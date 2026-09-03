# WP08 — Intégration OpenHands

> **Contexte** : plateforme locale d'agents IA pour le pricing de dérivés, sur serveur
> Debian avec 2 × V100. Le modèle est servi par **llama.cpp** sur
> `http://127.0.0.1:8000/v1` (OpenAI-compatible), contexte 32K. Quatre serveurs MCP
> exposent le moteur C++/l'analyse de code, le RAG et la mémoire.
>
> **OpenHands est le harness.** On ne réécrit ni la boucle agentique, ni l'exécuteur
> d'outils, ni le gestionnaire d'état. Ce work package **configure et câble**.

**Fichiers à lire** : ce fichier · [01-ARCHITECTURE.md](../01-ARCHITECTURE.md) §1 et §6 ·
[05-SEQUENCES.md](../05-SEQUENCES.md) §5, §6, §8 · [06-CONFIG.md](../06-CONFIG.md) §5

**Dépend de** : WP00, WP03, WP06, WP07. **Bloque** : WP09 (runner agent).

> **Implémenté et vérifié (2026-09-03)** sur le serveur réel (Debian, 2×V100).
> Tous les `[À CONFIRMER]` ci-dessous ont été résolus contre la documentation
> officielle (docs.openhands.dev) et/ou vérifiés empiriquement — voir chaque
> section. Un écart réel par rapport à l'intention d'origine du blueprint a été
> découvert et est documenté explicitement en §5/§9 plutôt que masqué : le CLI
> OpenHands **n'a pas de sandbox Docker en mode headless**.

---

## 1. Objectif

Obtenir un agent qui : parle au LLM local, dispose des outils MCP, exécute le code
(directement sur l'hôte en CLI headless — voir §5 pour l'écart par rapport à
l'isolation Docker initialement prévue), travaille sur une branche Git dédiée, et
voit ses actions sensibles refusées techniquement plutôt que soumises à une
approbation humaine native (voir §9).

---

## 2. Installation

| Étape | Commande / action | Vérification |
|---|---|---|
| 1 | Installer `uv` (procédure officielle) | `uv --version` |
| 2 | `uv tool install openhands --python 3.12` (installe aussi `openhands-acp`) | `openhands --version` → `1.16.0` (SDK `1.21.0`) |
| 3 | Binaire installé à `~/.local/bin/openhands` ; ajouter `~/.local/bin` au `PATH` | `command -v openhands` |
| 4 | Usage scripté/headless : exporter `OPENHANDS_SUPPRESS_BANNER=1` (sinon une bannière de démarrage pollue stdout) | — |
| 5 | GUI (non utilisé par ce WP, cf §5) | `openhands serve` → `http://localhost:3000` |
| 6 | Accès distant au GUI, si utilisé un jour | tunnel SSH `ssh -L 3000:localhost:3000 user@server` — **jamais** d'exposition publique |

Ce WP utilise exclusivement le **CLI headless** (`openhands --headless --json -t "..."`),
pas le GUI `serve`. C'est un choix structurant : voir §5.

---

## 3. Connexion au LLM local

```text
Provider : OpenAI-compatible
Base URL : http://127.0.0.1:8000/v1
API key  : "local-llm" (placeholder ; llama-server n'impose pas de vraie clé)
Model    : openai/<served_name de configs/models.yaml>
```

Le CLI headless tourne **nativement sur l'hôte** (pas de conteneur, cf. §5) : la
connexion au LLM local se fait donc directement en `127.0.0.1`, sans
`host.docker.internal` ni `--add-host`. Ces préoccupations (`docker run --add-host
host.docker.internal:host-gateway ...`) restent pertinentes seulement si `openhands
serve` (GUI, Docker) est utilisé un jour — non exercé par ce WP.

Configuration réelle, dans `~/.openhands/agent_settings.json` (schéma confirmé via
`docs.openhands.dev/openhands/usage/cli/command-reference.md`) :

```json
{"llm": {"model": "openai/Qwen3-Coder-30B-A3B-Instruct",
         "api_key": "local-llm",
         "base_url": "http://127.0.0.1:8000/v1"}}
```

Ce fichier n'est **jamais édité à la main** : il est entièrement régénéré par
`infra/scripts/render-openhands-config.sh`, qui lit `configs/models.yaml` (`active`,
`served_name`, `host`, `port`) — miroir du principe déjà appliqué par
`render-llama-env.sh`.

**Bug découvert et corrigé pendant l'implémentation** : `run-llama-server.sh` ne
passait jamais `LLAMA_SERVED_NAME` comme `--alias` au binaire `llama-server`, donc
`/v1/models` exposait le chemin brut du fichier `.gguf` au lieu du `served_name`
stable — ce qui aurait cassé la convention `openai/<served_name>` d'OpenHands.
Corrigé dans `infra/scripts/run-llama-server.sh` **et** redéployé manuellement vers
`/opt/llm/scripts/run-llama-server.sh` (la copie réellement référencée par le
`ExecStart` systemd — **ce sont deux fichiers distincts sur disque**, un `git pull`
seul ne suffit pas à mettre à jour le service). Vérifié via `curl
http://127.0.0.1:8000/v1/models`.

| Règle |
|---|
| Aucun fallback vers une API distante. Si le LLM local est down, l'agent échoue. |
| Le `served_name` vient de `configs/models.yaml`, jamais recopié en dur. |
| Budget de contexte applicatif aligné sur `ctx_size` (32768). Changer le modèle = changer `configs/models.yaml` + relancer `render-llama-env.sh`/`run-llama-server.sh` + `render-openhands-config.sh` ; aucun fichier OpenHands n'est touché à la main. |

---

## 4. Câblage MCP

Déclarés via le CLI (`openhands mcp add/list/get/remove/enable/disable`), jamais en
éditant `~/.openhands/mcp.json` à la main. Transport `stdio` uniquement — confirmé
empiriquement que les serveurs sont lancés comme sous-process directs de l'hôte (pas
dans un conteneur), cf. §5.

> Le `quantlab` de la maquette d'origine n'a jamais été construit. Les 4 serveurs
> réellement livrés et câblés ici sont ceux de `configs/mcp/*.yaml` (voir
> [blueprint/README.md](../README.md) « Correctif de périmètre ») :

| Serveur | Transport | Commande enregistrée | Outils |
|---|---|---|---|
| `agentmem` | `stdio` | `uv run --directory <repo> agentmem-mcp` | `mem.*` |
| `codeintel` | `stdio` | `uv run --directory <repo> codeintel-mcp` | `code.*` |
| `cppdev` | `stdio` | `uv run --directory <repo> cppdev-mcp` | `cpp.*` |
| `kbase` | `stdio` | `uv run --directory <repo> kbase-mcp` | `kb.*` |

Enregistrement automatisé par `infra/scripts/render-openhands-config.sh`, qui
énumère `configs/mcp/*.yaml` (`transport: stdio`) et fait
`openhands mcp remove <name> || true` puis `openhands mcp add <name> --transport
stdio uv -- run --directory <repo> <name>-mcp` pour chacun. Idempotent.

**Deux bugs découverts et corrigés** pendant le premier smoke test (§11) :

1. `uv run --project <repo>` ne change **pas** le répertoire de travail (seul
   `--directory` le fait, confirmé via `uv run --help`) ; or `corelib.config.Settings`
   lit son `.env` relatif au CWD du process. Les 4 serveurs MCP plantaient donc au
   démarrage (`corelib.errors.ConfigError`, 12 champs manquants) dès qu'OpenHands
   les lançait depuis un CWD différent de la racine du repo. Corrigé :
   `render-openhands-config.sh` utilise maintenant `--directory`, pas `--project`.
2. **Critique** : `corelib/logging.py` écrivait ses logs JSON sur **stdout**
   (`logging.StreamHandler(stream=sys.stdout)`). Pour un serveur MCP en transport
   `stdio`, stdout est réservé **exclusivement** aux trames JSON-RPC — toute ligne
   de log qui s'y mélange corrompt le parseur côté client OpenHands
   (`pydantic_core.ValidationError` dans `mcp/client/stdio.py`, observé en réel avec
   une ligne de log `agentmem-mcp` « procedures synced from git »). Corrigé :
   `corelib/logging.py` écrit maintenant sur **stderr**. Ce bug touchait les 4
   serveurs MCP (tous partagent `corelib.logging.get_logger`), pas seulement celui
   qui l'a révélé.

Test de recette (vérifié, en appelant directement chaque serveur en stdio, un vrai
appel outil par serveur) : `mem.list_procedures` (agentmem), `code.outline`
(codeintel — erreur applicative attendue sur ce repo Python sans
`compile_commands.json`, mais round-trip JSON-RPC réussi), `cpp.targets` (cppdev),
`kb.stats` (kbase) → les 4 répondent correctement.

> **Ne pas exposer des dizaines d'outils d'un coup.** Chaque outil ajouté augmente la
> taille du contexte et la surface d'erreur. Les profils (§6) n'allowlistent que les
> outils nécessaires à leur rôle.

---

## 5. Sandbox Docker — écart confirmé par rapport à l'intention d'origine

> **Constat confirmé (pas une hypothèse)** : le CLI OpenHands 1.16.0, en mode
> `--headless`, **n'a aucune option de sandbox Docker**. `openhands --help` ne liste
> de Docker que sur le sous-commande `serve` (« Launch the OpenHands GUI server
> using Docker »), un chemin de code entièrement différent (backend
> `ghcr.io/openhands/agent-server:*`) que ce WP n'exerce pas. Vérifié empiriquement
> pendant le smoke test (§11) : `docker ps -a` ne montre jamais de conteneur
> agent-server créé, et les édits/commits de l'agent apparaissent directement dans
> le repo hôte (`/srv/repos/agent-smoke-test`) — preuve que `terminal`/`file_editor`
> s'exécutent comme sous-process directs de l'utilisateur qui lance `openhands`.

Ceci **contredit** le mandat initial de cette section (« Docker sandbox obligatoire »).
Décision documentée pour la phase 1 de WP08, plutôt que masquée :

| Décision | Justification |
|---|---|
| Le CLI headless est utilisé **tel quel, sans isolation Docker**. | C'est le seul mode qu'expose l'outil réellement installé ; construire/adapter une image `agent-server` custom (cf. la doc SDK `openhands-agent-server`, `docker buildx build --target binary`) est un effort disproportionné pour ce WP et reste possible plus tard si nécessaire. |
| La frontière de sécurité repose entièrement sur les **hooks** (§9) + la discipline OS. | `--llm-approve` n'existe pas en headless (§9) : sans hook, un push/merge/`rm -rf` serait auto-approuvé silencieusement. |
| Recommandation pour tout usage au-delà d'un smoke test ou d'une tâche de confiance : lancer l'agent sous un **utilisateur OS dédié, non-privilégié**, sans accès aux credentials cloud/production, et limiter les repos accessibles à `/srv/repos/*`. | Substitut partiel à l'isolation conteneur — ne protège pas contre tout, mais réduit la surface. |
| Si une isolation forte redevient nécessaire : évaluer `openhands serve` (GUI, Docker) plutôt que retenter une sandbox pour le CLI headless. | Le GUI est le seul chemin de code réellement sandboxé côté OpenHands 1.x. |

| Règle (ce qui reste vrai indépendamment du point ci-dessus) |
|---|
| Jamais de credentials cloud, clé SSH (`~/.ssh`) ou password store accessibles depuis l'environnement où tourne l'agent. |
| Depuis l'environnement de l'agent : accès direct à PostgreSQL (5432), `llama-server` (8000) et aux serveurs MCP — **attendu** puisqu'il n'y a pas de frontière réseau conteneur ; ne pas y voir un manquement, mais la conséquence du point ci-dessus. |
| `/`, `/etc`, `/home` d'autres utilisateurs : jamais accessibles en écriture par l'utilisateur OS dédié à l'agent. |

---

## 6. Profils d'agents

Les rôles ne sont pas des processus : ce sont des configurations.
Source : `agents/profiles/*.yaml` (voir [06-CONFIG.md](../06-CONFIG.md) §5).

| Profil | Outils MCP | Écriture | Terminal | Git |
|---|---|---|---|---|
| `orchestrator` | tous | non | non | non |
| `research` | `kb.*`, `mem.recall` | non | non | non |
| `quant` | `cpp.build/test/bench/targets`, `code.find_symbol/definition/outline/signature`, `kb.search/get_equation`, `mem.recall` | non | non | non |
| `coding` | fs, terminal, git, `cpp.*`, `code.*` | `/workspace` | oui | commit oui, push non |
| `validation` | `cpp.test`, pytest | non | restreint | non |

**Phase 1 : un seul profil actif à la fois, un agent, un repo.** (« une sandbox » n'a
plus de sens : cf. §5, il n'y a pas de sandbox en mode CLI headless.)
Le multi-agent simultané n'est pas activé.

**Résolu** : chaque `agents/profiles/*.yaml` porte désormais un bloc
`openhands_mapping` qui traduit concrètement ce tableau :

```yaml
openhands_mapping:
  mcp_servers_enabled: [kbase, agentmem]      # openhands mcp enable <name>
  mcp_servers_disabled: [codeintel, cppdev]   # openhands mcp disable <name>
  confirmation_mode: always-approve            # seul mode dispo en headless (§9)
  native_tools_caveat: >
    Pas de blocage natif filesystem/terminal par profil en CLI headless 1.x ; les
    restrictions écriture/terminal/git du tableau ci-dessus sont des conventions de
    prompt, renforcées uniquement pour git push/merge/force/reset --hard/rm -rf par
    le hook PreToolUse block_dangerous.sh (§8/§9).
```

Seul le blocage de serveurs MCP entiers (`mcp_servers_enabled/disabled`) est une
restriction *techniquement* appliquée par OpenHands ; le reste (allowlist d'outils
fins au sein d'un serveur, écriture limitée à `/workspace`, terminal désactivé) est
porté par le prompt système + les hooks, pas par un mécanisme natif par profil.

---

## 7. Skills / prompts

**Résolu** : le terme OpenHands 1.x est « skills », pas « microagents ». Deux
mécanismes distincts, confirmés via `docs.openhands.dev` :

| Mécanisme | Chemin | Format | Chargement |
|---|---|---|---|
| Skill déclenchée par mot-clé/chemin | `.agents/skills/<name>/SKILL.md` | frontmatter YAML (`name`, `description` commençant par « This skill should be used when... », `triggers: [...]` ou `paths: [...]`) + corps impératif | à la demande, quand un trigger matche |
| Contexte toujours chargé | `AGENTS.md` (racine du repo) | markdown libre, frontmatter optionnel (`agent:`, défaut `CodeActAgent`) | systématique, chaque session |

Correspondance avec les noms de la maquette d'origine :

| Ancien nom (maquette) | Fichier réel livré |
|---|---|
| `repo.md` | `AGENTS.md` (racine repo, + template générique dans `agents/openhands-template/AGENTS.md.template`) |
| `quant-conventions.md` | `.agents/skills/quant-conventions/SKILL.md` |
| `rag-citation.md` | `.agents/skills/rag-citation/SKILL.md` |
| `git-checkpoint.md` | `.agents/skills/git-checkpoint/SKILL.md` |

Le socle commun (`agents/prompts/system-common.md` + `agents/prompts/snippets/
{research,quant,coding,validation}.md`, référencés par `system_prompt` dans les
profils §6) porte les règles universelles : ne jamais inventer un nom d'outil/modèle,
citer `kb.search` avant d'énoncer une formule, petites étapes revues, mémoire via
`mem.recall`/`mem.remember`.

Ces prompts/skills sont la principale défense **comportementale**. Ils ne remplacent
pas les gardes techniques (allowlist MCP par serveur, hooks), qui restent la
défense **effective** — d'autant plus depuis le constat de §5 (pas de sandbox).

Modèle réutilisable : `agents/openhands-template/` (voir son propre `README.md`)
contient hooks + skills + `AGENTS.md.template`, à copier (`cp -r`) dans tout nouveau
repo cible puis à compléter (contenu réel d'`AGENTS.md`, éventuel hook `Stop`
exigeant des tests verts, `.openhands/setup.sh`).

---

## 8. Discipline Git

```text
main
 └── agent/task-YYYYMMDD-<slug>
        ├── commit — étape 1
        ├── commit — étape 2
        └── commit — tests verts
```

| Règle |
|---|
| Vérifier `git status` / `git branch` avant toute tâche autonome. |
| Créer automatiquement la branche de travail (skill `git-checkpoint`, §7). |
| Jamais de commit direct sur `main`. |
| Un commit laisse le repo dans un état où les tests passent. |
| `git push`, merge, force-push, `reset --hard` : **refusés techniquement**, pas seulement « approbation requise » — voir §9, le mode headless n'a pas de vraie approbation humaine possible. |

---

## 9. Politique d'approbation humaine — résolu, avec un écart important

> **Confirmé** (`docs.openhands.dev/openhands/usage/cli/headless.md`) : `--llm-approve`
> **n'est pas disponible en mode headless**. `openhands --headless` tourne toujours en
> auto-approbation totale (équivalent `--yolo`), quelle que soit la CLI utilisée pour
> le lancer. Il n'existe donc **aucune** « demande d'approbation humaine » possible au
> sens propre dans ce mode — un `git push` ne produira jamais de prompt de
> confirmation, il serait silencieusement exécuté.

La politique du tableau ci-dessous n'est donc **pas** mise en œuvre par un mécanisme
d'approbation OpenHands (il n'existe pas en headless), mais par un **refus dur et
inconditionnel** : un hook `PreToolUse` (`.openhands/hooks/block_dangerous.sh`, cf.
`agents/openhands-template/`) inspecte chaque commande `terminal` et répond
`exit 2` + `{"decision": "deny", "reason": "..."}` sur les motifs dangereux — ce que le
protocole hooks (confirmé via `docs.openhands.dev/openhands/usage/customization/
hooks.md`) traite comme un blocage ferme, non contournable par l'agent. Testé et
vérifié en réel : `git push` → refusé (`exit=2`) ; `git status` → autorisé (`exit=0`).
Couvre aussi : `git merge`/`rebase`, `--force`/`-f`, `git reset --hard`,
`rm -rf`/`rm -fr`, et l'accès à des chemins secrets (`.ssh/`, `.env*`, `id_rsa`,
`/etc/shadow`).

| Autonome (hors interception hook) | Refusé techniquement par le hook |
|---|---|
| lecture de code, édition dans le repo, tests, compilation, lint, `git diff`, commit | `git push` (toute forme), merge, rebase, force, `git reset --hard`, `rm -rf`, accès à des chemins secrets |

> **La politique vit dans des fichiers du host** (`.openhands/hooks/`), hors de tout
> « workspace » applicatif au sens conteneur (qui n'existe pas ici, cf. §5). Le modèle
> peut techniquement lire/éditer ces fichiers puisqu'il n'y a pas d'isolation — la
> défense repose sur le fait que le hook s'exécute **avant** chaque action et que la
> modifier n'empêche pas le refus courant. Un contournement (l'agent édite le hook
> puis relance) reste possible sans surveillance humaine ; documenté comme limite
> connue plutôt qu'ignoré.

---

## 10. Hooks de mémoire

| Moment | Action |
|---|---|
| Début de tâche | `mem.recall(objectif)` → injecter les épisodes pertinents dans le contexte initial |
| Fin de tâche | `mem.remember(épisode, confirm=true)` avec objectif, actions, résultat, **leçons** |

**Résolu** : il n'existe pas de mécanisme OpenHands qui déclenche automatiquement
`mem.recall`/`mem.remember` — les hooks (`PreToolUse`/`PostToolUse`/`Stop`/
`SessionStart`/`SessionEnd`) sont un mécanisme générique, déjà utilisé ici pour le
blocage git (§9) et la vérification de tests (§11), pas spécifique à la mémoire.
`mem.recall`/`mem.remember` restent donc des **appels explicites**, prescrits par
`agents/prompts/system-common.md` et laissés à l'initiative de l'agent — une défense
comportementale, pas technique (cohérent avec le constat de §7).

---

## 11. Smoke test — critère de recette principal (exécuté et réussi)

Repo de test : `/srv/repos/agent-smoke-test` avec `README.md`, `AGENTS.md`, `src/`,
`tests/`, le template de hooks/skills (§7) appliqué + un hook `Stop`
(`require_tests.sh`) exigeant que `pytest` passe avant de considérer la tâche finie.

Tâche donnée à l'agent (`openhands --headless --json -t "..."`) :

> Inspecte ce repository (lis `README.md`/`AGENTS.md`), ajoute `is_palindrome(s: str)
> -> bool` à `stringutils` (insensible casse/espaces), écris des tests pytest,
> lance-les, corrige toute erreur, puis crée un commit sur une branche dédiée
> (pas sur `main`).

**Résultat réel, vérifié** :

```text
read (find + cat README/AGENTS.md) → edit (is_palindrome) → run tests (pytest) →
git checkout -b agent/task-smoke-test → git commit (b79cec7)
```

- `is_palindrome` implémentée (plus robuste que demandé : ignore aussi la ponctuation).
- 11 tests pytest ajoutés (14 au total avec les 3 préexistants), tous verts.
- Commit `b79cec7` sur la branche `agent/task-smoke-test`, **`main` intact**
  (`git log --oneline --all` le confirme).
- Hook `PreToolUse` (`block_dangerous.sh`) déclenché sur chacune des 18 commandes
  terminal de la trajectoire, jamais bloqué à tort.
- Une tentative manuelle ultérieure de `git push origin agent/task-smoke-test` dans
  ce même repo est refusée par le hook (`exit=2`) — vérifié séparément (§9).

**Anomalie observée, non bloquante** : la conversation s'est terminée par une
`LLMContextWindowExceedError` (32768 tokens, dépassé de ~200 tokens) pendant une
relecture finale redondante du fichier — **après** que le commit a déjà réussi. Le
hook `Stop` (`require_tests.sh`) n'a donc jamais eu l'occasion de s'exécuter dans ce
run (il a été vérifié séparément, manuellement). Enseignement : avec `ctx_size=32768`
et des hooks verbeux sur chaque commande, une trajectoire avec beaucoup d'itérations
peut approcher la limite — garder les tâches petites, ou augmenter `ctx_size` si le
modèle servi le permet.

> Ce smoke test est **plus important que le simple chargement du modèle** — confirmé :
> c'est lui qui a révélé les deux bugs MCP critiques du §4.

---

## 12. Critères d'acceptation

- [x] OpenHands démarre et atteint le LLM local — **sans conteneur** : connexion directe `127.0.0.1:8000` depuis le process host (§3/§5).
- [x] Les **quatre** serveurs MCP (substitution `quant.*` → `cpp.*`+`code.*`, cf. §4) sont listés ; un appel réel réussit sur chacun (vérifié en direct stdio : `mem.list_procedures`, `code.outline`, `cpp.targets`, `kb.stats`).
- [ ] ~~La sandbox Docker démarre, `/workspace` monté, utilisateur non-root.~~ **Non applicable** : pas de sandbox Docker en CLI headless (§5, écart documenté, pas une case à cocher plus tard sans changer d'outil/mode).
- [ ] ~~Depuis la sandbox : pas d'accès à PostgreSQL, `llama-server`, MCP, `~/.ssh`, `/etc`.~~ **Non applicable** pour la même raison ; mitigation : utilisateur OS dédié (§5).
- [x] L'agent édite du code, lance les tests, corrige une erreur, crée un commit (§11).
- [x] Une tentative de `git push` est bloquée — pas par une « demande d'approbation » (impossible en headless, §9) mais par un **refus dur** (`exit 2`) du hook `PreToolUse`, vérifié.
- [ ] ~~Aucun secret du host n'est visible depuis la sandbox.~~ **Non applicable** (pas de sandbox) ; risque réel, mitigé par discipline OS uniquement (§5).
- [ ] Les services remontent après reboot — non re-vérifié dans cette session (unités systemd déjà livrées en WP00/WP06/WP07 pour `llama-server` et les serveurs MCP ; à revalider explicitement).
- [x] Changer `active` dans `configs/models.yaml` + relancer `render-llama-env.sh`/`run-llama-server.sh` (redémarre `llama-server`) + `infra/scripts/render-openhands-config.sh` suffit à changer de modèle, sans toucher au code.

---

## 13. Pièges

| Piège | Conduite à tenir |
|---|---|
| Le CLI headless n'a pas de sandbox Docker (§5) | ne pas supposer d'isolation conteneur ; utilisateur OS dédié + hooks comme seule vraie frontière |
| `--llm-approve` indisponible en headless (§9) | remplacer par un hook `PreToolUse` à refus dur, pas par une politique de confirmation |
| `uv run --project` ne change pas le CWD, seul `--directory` le fait | tout code qui résout un chemin relatif au CWD (ex. `corelib.config.Settings` et son `.env`) doit être lancé avec `--directory` |
| Un serveur MCP stdio qui log sur **stdout** corrompt le JSON-RPC | `corelib.logging` écrit sur **stderr** ; règle générale pour tout futur serveur MCP stdio |
| Script de service (ex. `run-llama-server.sh`) modifié dans le repo mais pas redéployé | un service systemd référence une copie déployée (`/opt/llm/scripts/...`), distincte du repo — redéployer explicitement après chaque fix |
| Trop d'outils exposés d'emblée | allowlist stricte par profil (§6), élargir progressivement |
| Le modèle invente des noms de modèles/méthodes | imposer dans le prompt de passer par `code.*`/`cpp.*` réels, jamais un nom inventé |
| Le modèle recopie un chiffre au lieu d'appeler l'outil | test de recette dédié : toute valeur numérique doit avoir un `run_id` |
| Contexte saturé (`LLMContextWindowExceedError`, observé en réel à 32768, §11) | réduire `k` RAG, activer le reranking, limiter `max_result_bytes`, garder les tâches petites |
| Tâche longue perdue en cas de crash | s'appuyer sur les commits Git comme checkpoints, et sur `mem.remember` |
