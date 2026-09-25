# WP08f — « Démarrer la session » lance toute la pile, sans terminal

> **But.** Un clic sur *Start Session* dans l'extension doit lever tout ce qu'il
> faut — `openhands-bridge`, `llama-server`, le socket `llama-bridge`, Docker si
> besoin — puis démarrer la session. **Sans** ouvrir un terminal et y taper des
> commandes (`sudo systemctl …`, `uv run openhands-bridge`) comme le fait le
> panneau « Components » aujourd'hui.

**Repo jumeau** : `agenticenv-chat` (le pré-vol + le déclenchement silencieux).
**Issues** : agenticenv-chat#… (client), pas d'issue bridge (infra livrée ici).

---

## 1. État actuel

- `openhands-bridge` : lancé **à la main** (`uv run openhands-bridge` dans un
  terminal VS Code). Pas de service.
- `llama-server` : service **système** (`WantedBy=multi-user.target`, user `llm`),
  root requis pour `systemctl start`.
- `llama-bridge.socket` / `.service` : système, socket-activé, idle-exit 5 min.
- Panneau « Components » de l'extension : `actionCommand()` renvoie une **chaîne
  shell**, `runHealthAction()` fait `createTerminal(); term.show(); term.sendText(cmd)`
  → un terminal s'ouvre, et `sudo systemctl …` y demande le mot de passe.
- **Pas de polkit sur l'hôte** (`pkexec` absent) → le mécanisme sans mot de passe
  est **sudoers NOPASSWD**, pas une règle polkit.

## 2. Livré côté AgenticEnv (`infra/`)

| Fichier | Rôle |
|---|---|
| `infra/systemd/agenticenv-bridge.service` | unit **`systemctl --user`** pour le bridge (uid 1000 obligatoire : WP08d write-back, accès docker, `gh`, checkout). `Restart=on-failure`, `WantedBy=default.target`. |
| `infra/sudoers.d/agenticenv-stack` | NOPASSWD **étroit** : `start`/`stop`/`restart`/`is-active` sur `llama-server.service`, `llama-bridge.{socket,service}`, `docker.service` — rien d'autre, pas de wildcard, pas de shell. |
| `infra/scripts/install-desktop-stack.sh` / `just install-stack` | pose le unit user (`+ enable`, `+ loginctl enable-linger`), valide et installe le sudoers (`visudo -cf`). Re-jouable. |

Après `just install-stack` :
- `systemctl --user start agenticenv-bridge` — silencieux, survit aux
  déconnexions (linger), logs dans `journalctl --user -u agenticenv-bridge`.
- `sudo -n systemctl start llama-server` — silencieux.

## 3. Reste à faire côté client (`agenticenv-chat`)

### 3.1 `runHealthAction` sans terminal

- `actionCommand()` : renvoyer un `{argv: string[]}` structuré au lieu d'une
  chaîne shell.
  - `bridge` → `["systemctl", "--user", "start", "agenticenv-bridge"]`
  - `llama-server` → `["sudo", "-n", "systemctl", action, "llama-server.service"]`
  - `llama-bridge` → `["sudo", "-n", "systemctl", "start", "llama-bridge.socket"]` (start) / `["sudo", "-n", "systemctl", action, "llama-bridge.service"]`
  - `docker` → `["sudo", "-n", "systemctl", "start", "docker.service"]`
  - `agent-server-image` → `["docker", "pull", <image>]`
- `runHealthAction()` : `execFile(argv[0], argv.slice(1))` (le helper `run()` de
  `health.ts` existe déjà), **plus** de `createTerminal`. Toast de progression
  (« Starting llama-server… » — le chargement du modèle prend ~30 s).
- **Repli** : si `execFile` échoue avec `sudo: a password is required` ou
  `Unit … not found` → notice actionnable « lance `just install-stack` dans
  AgenticEnv » + bouton « Copier la commande » / « Ouvrir un terminal » (l'ancien
  comportement, mais choisi explicitement, pas imposé).

### 3.2 Pré-vol de « Start Session »

Sur clic *Start Session*, avant d'ouvrir la WebSocket :
1. `checkHealth()` → composants `down` qui ont une action `start`.
2. Les démarrer en séquence (docker → llama-server → llama-bridge → bridge),
   toast de progression, `execFile` silencieux.
3. Poller `checkHealth()` jusqu'à : bridge joignable **et** `llama-server`
   répond `/health` (timeout ~90 s, le modèle est lent à charger).
4. Puis connexion WS + `hello` + `start_session` comme aujourd'hui.
5. Si un composant ne démarre pas → arrêter là, notice actionnable (§3.1 repli),
   ne pas laisser un spinner tourner dans le vide.

### 3.3 Détails

- L'extension doit savoir si `install-stack` a été fait : feature-detect en
  tentant `systemctl --user is-active agenticenv-bridge` ; `Unit not found` →
  proposer l'install une fois, mémoriser le refus.
- `agenticEnvPath` (déjà dans `HealthContext`) donne le cwd pour les messages.
- Ne rien lancer automatiquement **sans** le clic : pas de démarrage au
  chargement de l'extension.

## 4. Vérification

- `just install-stack` sur l'hôte → `systemctl --user status agenticenv-bridge`
  actif, `sudo -n systemctl is-active llama-server` sans mot de passe.
- Extension : arrêter tous les composants, cliquer *Start Session*, voir la pile
  se lever (toasts) puis la session démarrer, **aucun terminal ouvert**.
- Couper le sudoers → *Start Session* échoue proprement avec la notice d'install.
