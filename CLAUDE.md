# AgenticEnv — notes pour Claude Code

Atelier de dev agentique **local** : `packages/openhands_adapter` (SDK OpenHands +
sandbox Docker pilotant `llama-server`), `packages/openhands-bridge` (serveur
WebSocket exposé à un client de chat), les serveurs MCP (`*-mcp`), `corelib`.

**Repo jumeau** : [`agenticenv-chat`](https://github.com/HadrienT/agenticenv-chat)
— l'extension VS Code qui parle au bridge. Les deux évoluent ensemble ; le
protocole du fil est `packages/openhands-bridge/src/openhands_bridge/protocol.py`,
miroité manuellement dans `agenticenv-chat/src/protocol.ts` (test de dérive côté
client).

## Suivi du travail — GitHub Issues, pas de markdown de handoff

Le « JIRA » du projet, ce sont les **GitHub Issues des deux repos**. `gh` est
authentifié (compte `HadrienT`).

- **Au démarrage d'une session** : `gh issue list --state open` sur **ce repo** ET
  sur `HadrienT/agenticenv-chat`. Chaque repo a une issue épinglée
  **`📋 Board`** qui agrège tout (AgenticEnv#9, agenticenv-chat#3).
- **Une tâche ou un bug qui concerne l'autre repo** →
  `gh issue create --repo HadrienT/agenticenv-chat …`. **Jamais** un fichier
  markdown de passation.
- **Issue traitée** → `gh issue close <n> --repo … --comment "fait dans <sha>"`,
  et cocher la case correspondante dans le Board.
- **Labels** : `cross-repo` (coordination), `blocked` (attend l'autre repo),
  `needs-verification` (code fait, reste un test manuel), `from-bridge` /
  `from-client`.
- Les gros morceaux de **conception** restent dans `blueprint/wp/*.md` ; l'issue y
  renvoie, elle ne les remplace pas.

## Commandes

| | |
|---|---|
| `just lint` | ruff + `mypy --strict` par paquet + import-linter — **vert avant tout commit** |
| `just test` | pytest (hors `integration` / `e2e`) |
| `just test-e2e` | smoke OpenHands (Docker + `llama-server` requis, hors CI) |
| `just run-bridge` | lance le bridge WebSocket sur `127.0.0.1:8300` |

## Divers

- **Conversation avec le mainteneur : en français.** Code, identifiants, messages
  de commit : en anglais. `blueprint/` est déjà en français.
- **Réseau Docker fragile sur l'hôte de dev** : un teardown de veth sur le bridge
  `docker0` par défaut a déjà figé l'hôte et coupé tout le LAN. Ne jamais faire
  de `docker rm -f` en masse ; agir un conteneur à la fois, en expliquant le
  rayon d'impact. Cf. issue #8.
- Commits : passer par une branche, pas directement sur `main`. Terminer les
  messages de commit par `Co-Authored-By: Claude <noreply@anthropic.com>`.
