# WP17 — Viser le niveau Claude Code / Codex

> **Objectif de l'opérateur (2026-10-31)** : un outil aussi performant que ceux
> d'Anthropic ou d'OpenAI. Ce WP vient **après** WP10 à WP16 : sans outils branchés
> ni fiabilité, aucune de ces fonctions n'apporte de résultat.
>
> **Limite à garder en tête** : ces produits doivent une grande part de leurs résultats
> à leurs modèles. L'outillage peut atteindre leur niveau. Le modèle local, un 30B en
> Q4 sur deux V100, reste à mesurer. D'où l'évaluation (§1) avant tout le reste.

**Fichiers à lire** : ce fichier · [WP08e](WP08e-multi-conversation-resume.md) ·
`agenticenv-chat/docs/parity-copilot-claude-code.md` · `agenticenv-chat/docs/bridge-v2-spec.md`

**Dépend de** : WP11, WP12. **Côté client** : HadrienT/agenticenv-chat#16.

---

## 1. Banc d'évaluation de l'agent — #47

Sans mesure, on ne saura pas si une modification aide.

| Livrable |
|---|
| `benchmarks/agent/` : 12 tâches sur 3 petits projets (corriger un bug, ajouter une fonction, écrire des tests, refactor), chacune avec un critère de réussite exécutable. À porter à 30 avec des tâches sur quant-modeling une fois les premiers résultats lus. |
| Lanceur headless via `run_task`, répétitions, résultats en base `eval`. |
| Métriques : taux de réussite, tours, tokens, durée, boucles, erreurs d'appels d'outils. |
| Baseline avant WP12, puis mesure après chaque WP. |

**Baseline du 2026-10-31** : 10 tâches sur 12 (Qwen3 30B Q4, sans MCP), environ 2 minutes par tâche.

## 2. Modèle et débit — #48

| Livrable |
|---|
| Comparer sur le banc au moins 2 modèles de code récents (quantisation supérieure, ou plus gros en découpant sur les deux GPU), en réussite et en tokens/s. |
| Régler `ctx_size` (65536 configuré), cache de prompt, `--parallel`, seuil du condenseur. |
| Vérifier `native_tool_calling` et le format d'appel d'outils de chaque modèle. |
| Option à trancher par l'opérateur : profil cloud pour les tâches difficiles. Le projet reste local par défaut. |

## 3. Streaming — #49

**Constat** : `deltas` n'est pas annoncé alors que le client sait le traiter. L'utilisateur
attend chaque réponse sans rien voir.

| Livrable |
|---|
| `LLM(stream=True)` côté SDK, relais `event_delta`, capability `deltas`. Derrière `llm.stream` dans `configs/openhands.yaml`, désactivé tant que le passage par `RemoteConversation` n'a pas été vérifié sur un vrai sandbox. |

**Acceptation** : premier token visible en moins de 2 s après le début de génération.

## 4. Capabilities manquantes — #50

| Capability | Livrable |
|---|---|
| `compact` | compaction à la demande via le condenseur |
| `interrupt` | consigne utilisateur injectée pendant un tour |
| `todo` | relais du `task_tracker` vers le panneau |
| `models` | liste et bascule des profils `code` / `translate` (#16) |
| Plan mode | profil lecture seule produisant un plan validé avant exécution |

## 5. Hôte et sandbox synchronisés — #51

**Constat** : conséquence de WP08g, une édition faite par l'utilisateur dans VS Code
entre deux tours n'atteint pas la copie. L'agent travaille sur une version périmée
et finit en conflit.

| Livrable |
|---|
| Au début de chaque tour : les fichiers modifiés sur l'hôte sont poussés dans la copie, `applied` et hashes mis à jour, l'agent en est informé. |

**Acceptation** : l'utilisateur modifie un fichier entre deux tours, l'agent le voit et
aucun conflit n'apparaît.

## 6. Démarrage et isolation de tâches — #52

| Livrable |
|---|
| Image dérivée avec `rg`, `fd`, `cmake`, `clangd`, pour ne pas les réinstaller à chaque session (les outils listés dans `CLAUDE.md` manquent aujourd'hui). |
| Mesure et réduction du temps de démarrage d'une session. |
| Exploration en parallèle (`tool_concurrency_limit`, sous-agents) si le banc montre un gain. |
| Recherche web avec une politique de réseau compatible WP10. |
