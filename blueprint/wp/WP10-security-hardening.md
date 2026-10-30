# WP10 — Sécurisation du bridge et du sandbox

> **Contexte** : l'audit du 2026-10-30 montre que le bridge accepte n'importe quelle
> origine et que le sandbox est peu isolé. Depuis WP08g, ce que produit l'agent
> arrive dans le vrai repo sans relecture : ce WP passe **en premier**.

**Fichiers à lire** : ce fichier · [WP08b](WP08b-openhands-sandbox.md) ·
[WP08g](WP08g-auto-apply.md) · `packages/openhands-bridge/src/openhands_bridge/server.py` ·
`packages/openhands_adapter/src/openhands_adapter/docker_workspace.py`

**Dépend de** : WP08g. **Bloque** : WP12 (exposer des MCP HTTP sans ce WP élargit la surface).

> ⚠️ **Réseau Docker fragile** (issue #8) : pas de changement de réseau en masse,
> un conteneur à la fois, rayon d'impact expliqué avant tout `iptables` ou réseau.

---

## 1. Authentification du WebSocket — #21

**Constat vérifié** : aucun contrôle d'`Origin` ni jeton. Une connexion avec
`Origin: https://evil.example` reçoit `welcome`. Toute page ouverte dans un
navigateur local peut viser `ws://127.0.0.1:8300`, avec un `project_path` arbitraire
et, depuis WP08g, une écriture automatique dans ce repo.

| Livrable |
|---|
| Jeton aléatoire 256 bits généré au démarrage du bridge, écrit en `0600` dans `${XDG_STATE_HOME:-~/.local/state}/agenticenv/bridge.token`. |
| Connexion refusée sans jeton valide (comparaison à temps constant), avant tout traitement de message. |
| `serve(..., origins=[None, "vscode-webview://..."])` : rejet des origines web. L'extension se connecte depuis l'hôte Node, donc sans `Origin`. |
| `project_path` validé : dossier existant, ni `/`, ni `$HOME` lui-même, ni un chemin système. |
| Lecture du jeton côté client : HadrienT/agenticenv-chat#13. |

**Acceptation** : test avec `Origin` hostile refusé, sans jeton refusé, jeton faux
refusé, client légitime accepté. Bridge sans fichier de jeton lisible : refuse de démarrer.

## 2. Port de l'agent-server — #22

**Constat (lu dans le code, non testé en live)** : `-p {host_port}:8000` publie sur
toutes les interfaces, avec `api_key=None`. Docker contourne en général le pare-feu de
l'hôte. L'API de l'agent-server pourrait donc être joignable depuis le LAN sans jeton.

| Livrable |
|---|
| Publier sur `127.0.0.1:{host_port}:8000`. |
| `SESSION_API_KEY` aléatoire par session, passé au conteneur et à `RemoteWorkspace`. |
| Test unitaire sur la commande `docker run` générée (aucun `-p` sans `127.0.0.1`). |

**Acceptation** : sandbox lancé, le port répond sur `127.0.0.1`, pas sur l'IP LAN, et
refuse une requête sans clé.

## 3. Durcissement du conteneur — #23

| Risque | Livrable |
|---|---|
| Aucune limite de ressources | `--memory`, `--cpus`, `--pids-limit` lus depuis `configs/openhands.yaml` |
| Secrets du projet lisibles (`secrets/`, `.env`), `sudo` et Internet disponibles | liste d'exclusion configurable appliquée à la copie (montage hors `/workspace/source` ou masquage par volume vide), `.env*`, `secrets/`, `*.pem`, `id_rsa*` par défaut |
| Internet sortant sans contrôle | décision à prendre : réseau Docker dédié avec proxy allowlist (`pypi`, `npm`, `apt`, `github`). Voir la contrainte réseau ci-dessus : à concevoir seul, à tester hors heures. |
| Accès aux services de l'hôte via `host-gateway` | documenter ce qui est joignable depuis `docker0`, restreindre `llama-bridge` au sous-réseau du sandbox si possible |
| Image épinglée par tag | épingler par digest `sha256` dans `configs/openhands.yaml` |

**Acceptation** : une commande `cat secrets/*` dans le sandbox échoue sur un repo de
test, y compris avec `sudo`. Un processus qui consomme toute la RAM est tué sans
affecter l'hôte.

## 4. Non-objectifs

Pas de multi-utilisateur, pas de TLS sur `127.0.0.1`.
