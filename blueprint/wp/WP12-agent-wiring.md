# WP12 — Brancher l'agent : MCP, prompts, profils, garde-fous

> **Contexte** : l'agent du chat n'a ni outil MCP, ni prompt système, ni profil. Il
> a le terminal, l'éditeur de fichiers et le task tracker. Tout le reste du repo est
> construit, mais n'atteint pas l'agent. **C'est le WP au plus fort effet.**

**Fichiers à lire** : ce fichier · [WP08b](WP08b-openhands-sandbox.md) §Phase 2 ·
[WP08](WP08-openhands-integration.md) · `packages/openhands_adapter/src/openhands_adapter/session.py` ·
`packages/openhands-bridge/src/openhands_bridge/mcp_catalog.py`

**Dépend de** : WP10. **Bloque** : WP14, WP17 (évaluation agent).

---

## 1. MCP joignable depuis le sandbox — #27

**Constat** : `mcp_config` n'est jamais passé à `AgentSession`, `StartSession.mcp_servers`
est accepté puis ignoré, les serveurs sont en `stdio` et les unités `mcp-*` ne sont
pas installées.

| Livrable |
|---|
| `kbase` et `agentmem` en `streamable-http` sur l'hôte, en services `systemctl --user` (`agenticenv-mcp@`), liés à la passerelle `docker0`, derrière un jeton. |
| `cppdev`, `codeintel`, `qmharness` en `stdio` **dans** le sandbox : ils doivent voir la copie que l'agent édite, pas le repo hôte, en retard jusqu'à la fin du tour. Ils exigent l'image `infra/docker/agent` (`sandbox.code_tools: true`). |
| `_start_session` traduit `mcp_servers` en `mcp_config` réel. Le picker a enfin un effet. |
| Un serveur injoignable ne coûte pas la session : il est signalé dans `session_started.mcp_unavailable`. |

**Acceptation** : e2e où l'agent appelle `kb.search` et `cpp.build` et cite le résultat,
ligne présente dans `obs.tool_invocations`. Healthcheck : les MCP passent de `skipped` à `ok`.

## 2. Résolution de config indépendante du répertoire courant — #28

`kb.search` a échoué le 2026-10-26 avec `config file not found: configs/kbase.yaml`.

| Livrable |
|---|
| `corelib.config` résout `configs/` depuis une variable `AGX_REPO_ROOT` ou la racine détectée, jamais depuis le répertoire courant. |

## 3. Prompts et profils réellement chargés — #29

**Constat** : aucun code Python ne charge `agents/profiles/*.yaml` ni
`agents/prompts/*`. Les allowlists et permissions déclarées ne s'appliquent pas.

| Livrable |
|---|
| `agents/` chargé et validé par un schéma pydantic. |
| Prompt injecté via `Agent.agent_context` (SDK 1.21), avec `AGENTS.md` du repo cible et conventions du sandbox. |
| `StartSession.profile` ajouté au protocole, profils listés dans `mcp_servers.profiles`. Profil `coding` par défaut. Une session `read_only` garde le profil demandé : la copie reste jetable et rien n'atteint le repo. |
| Allowlist appliquée via `Agent.filter_tools_regex`. |
| Limites du profil appliquées (`max_iterations`, `timeout_seconds`). |
| `orchestrator` retiré ou implémenté. Sélecteur côté client : HadrienT/agenticenv-chat#15. |

**Acceptation** : test sur l'`Agent` construit pour chaque profil (outils et prompt
attendus). Fichier de profil invalide : erreur explicite au démarrage.

## 4. Garde-fous actifs par défaut — #30

**Constat** : `block_dangerous.sh` existe dans `agents/openhands-template/`, mais il
faut le copier à la main, et il n'est pas présent dans quant-modeling. Avec
`NeverConfirm` et WP08g, plus rien ne s'interpose. Il faut donc d'autres barrières.

| Livrable |
|---|
| Hook injecté dans chaque copie sandbox par l'adapter, sans modifier le repo cible. Refus de `git push`, `merge`, `rebase`, `reset --hard` et des écritures sous `.git/`. |
| Liste de chemins jamais écrits par `_sync_to_host` : `.git/`, `.github/workflows/`, `.env*`, `.vscode/tasks.json`, hooks, avec une sortie en `skipped`. |
| Vérifier que l'agent-server 1.21 exécute ces hooks. Sinon, alternative documentée (`security_policy`, wrapper). |

**Acceptation** : e2e où l'agent tente `git push` et échoue. Un test où il modifie
`.github/workflows/ci.yml` : le fichier n'atteint pas le repo et le client le voit.
