# WP08e — Plusieurs conversations, reprise avec état conservé

> **But.** Aujourd'hui le bridge est mono-session : un `AgentSession` = un
> conteneur agent-server = une conversation, détruit à la fermeture
> (`delete_on_close=True`). L'utilisateur veut **plusieurs conversations
> archivées, réactivables**, avec **l'état interne de l'agent conservé** (vraie
> reprise `resume`, pas un simple rejeu de transcript), et une **bascule
> instantanée** — mais **une seule conversation active à la fois** (llama-server
> sérialise la génération de toute façon).

**Dépend de** : WP08b (adapter + sandbox), WP08d (copie de travail),
protocole v2 (`09692e7`). **Repo jumeau** : `agenticenv-chat` (bouton « Resume »
et archive `ConversationStore` déjà en place — cf. son `blueprint/wp/C08`).

**Décisions utilisateur (2026-09-06)** :
- reprise = **vraie** (`resume`, état agent conservé) → conteneur long-lived +
  volume hôte + message `resume` ;
- concurrence = **une active à la fois**, bascule = pause + détache + rattache.

**Issues** : AgenticEnv#… (epic bridge), agenticenv-chat#… (câblage client).

---

## 1. Modèle cible

| Concept | Aujourd'hui | Cible WP08e |
|---|---|---|
| Conteneur agent-server | 1 par `AgentSession`, jeté à la fermeture | **1 long-lived** pour la durée du process bridge (voire au-delà, §3) |
| Conversation | 1, liée au conteneur, `delete_on_close=True` | **N**, indépendantes du cycle de vie du conteneur, archivées explicitement |
| Conversation active | la seule qui existe | **1 parmi N** ; les autres sont suspendues, pas détruites |
| Copie de travail (WP08d) | `/workspace/project` unique | **une par conversation** : `/workspace/project/<conversation_id>/` |
| `resume` | non implémenté (client en avance) | rattachement par `conversation_id` + rejeu des events depuis `last_seq` |

L'agent-server sait déjà héberger plusieurs conversations : elles vivent dans
`/workspace/conversations/<id>/` (+ `/workspace/bash_events/`). Le travail est
côté **adapter** (découpler conteneur et conversation) et **bridge** (état actif,
bascule, `resume`).

## 2. Adapter (`packages/openhands_adapter`)

Découper `AgentSession` en deux responsabilités :

1. **`SandboxHost`** (nouveau) — possède le conteneur (`AgenticEnvDockerWorkspace`),
   le monte, expose `workspace`, le nettoie une seule fois. Vit tant que le
   bridge vit. `delete_on_close` **retiré** pour les conversations.
2. **`Conversation` par id** — `SandboxHost.open_conversation(id=None)` crée, 
   `SandboxHost.attach_conversation(id)` rattache une conversation existante
   (`RemoteConversation` avec l'id connu ; vérifier que le SDK réhydrate depuis
   le disque du conteneur au redémarrage), `SandboxHost.archive_conversation(id)`
   la ferme proprement **sans** la supprimer côté serveur.
3. **Copie de travail par conversation** : `WorkingCopy` prend
   `/workspace/project/<id>` ; `initialize()` fait le `cp -a` une fois par id ;
   `refs/agenticenv/*` restent internes à cette copie.

`run_task()` / le chemin batch existant : garder tel quel (une conversation
éphémère, pas d'archive).

## 3. Persistance (survivre au redémarrage du bridge / du conteneur)

- Bind-mount `/workspace/conversations` **et** `/workspace/bash_events` sur un
  volume hôte : `~/.local/share/agenticenv/sandbox/{conversations,bash_events}`
  (hors repo, hors `/workspace/{source,project}`).
- Les copies de travail `/workspace/project/<id>` : **jetables**, pas
  persistées — au rattachement, `cp -a` depuis `/workspace/source` puis rejeu ;
  si l'utilisateur veut retrouver des éditions non appliquées, c'est via
  `apply_changes` (WP08d) avant de quitter, comme aujourd'hui.
- Point à vérifier tôt : l'agent-server réhydrate-t-il une conversation depuis
  son dossier disque si le conteneur est recréé sur le même volume ? Sinon,
  fallback = reprise légère (rejeu du transcript archivé côté client).

## 4. Bridge (`packages/openhands-bridge`)

### 4.1 État

`_session_owner` (booléen implicite) → `_active` : `{conversation_id, owner
connection, turn_id?}` + un `SandboxHost` unique partagé. `SESSION_BUSY` ne
s'applique plus qu'à *une deuxième connexion cliente* concurrente, pas à une
deuxième conversation.

### 4.2 `resume`

Client → `resume {conversation_id, last_seq}`. Bridge :
1. si une autre conversation est active et qu'un tour tourne → `pause()` +
   `turn_finished{reason:"cancelled"}` ;
2. `SandboxHost.attach_conversation(conversation_id)` ;
3. rejouer les events `seq > last_seq` (le bridge tient un buffer par
   conversation, borné ; au-delà, `conversation.state.events` + renumérotation) ;
4. `resumed {seq}` puis reprise du flux normal.

`seq` devient **par conversation** (persisté avec elle), pas par connexion —
conforme au primer client (« seq monotone connexion + conversation »).

### 4.3 Bascule

`start_session` ou `resume` pour un id ≠ actif → §4.2 étapes 1–2, puis
`session_started`/`resumed`. La conversation quittée reste ouverte côté
agent-server (suspendue).

### 4.4 Capabilities

`welcome` annonce `resume` en plus. Le client retire `resume` de
`CLIENT_AHEAD_OF_BRIDGE`.

### 4.5 Nouveaux messages (à ajouter au protocole, miroir `protocol.ts`)

| sens | message | charge utile |
|---|---|---|
| in | `resume` | `{conversation_id, last_seq}` *(déjà côté client)* |
| in | `list_conversations` | `{}` — pour peupler le sélecteur |
| in | `archive_conversation` | `{conversation_id}` |
| out | `resumed` | `{seq}` *(déjà côté client)* |
| out | `conversations` | `{items:[{conversation_id, title?, updated_at, turns, active}]}` |

## 5. Client (`agenticenv-chat`) — petit

C08 §1 a été écrit pour ça : *« le jour où le multi-session bridge existe, seul
le §1 change »*.

- Câbler le bouton **« Resume »** (déjà présent, gaté sur capability) →
  `resume {conversation_id, last_seq}`.
- **Sélecteur de sessions** : liste `list_conversations` ∪ archive locale, marque
  « active », clic = `resume`. Pas de N stores webview — « une active » = on
  réhydrate le store depuis l'archive au switch (déjà supporté par `load`).
- `archive_conversation` sur « fermer sans supprimer ».
- Retirer `resume` de `CLIENT_AHEAD_OF_BRIDGE` quand le bridge l'annonce.

## 6. Interaction avec les autres issues

- **#7 (SESSION_BUSY coincé)** et **#8 (conteneurs fuités)** : largement
  **résorbées** — un conteneur unique long-lived à cycle de vie explicite est le
  bon correctif pour les deux. Réduit aussi la churn de veth sur `docker0`
  (moins de création/destruction de conteneurs → moins de risque de freeze hôte).

## 7. Vérification

- `just lint` / `just test` verts ; tests adapter (ouvrir 2 conversations sur un
  `SandboxHost` mické, basculer, vérifier l'isolement des copies de travail) ;
  test bridge `resume` (rejeu depuis `last_seq`, une connexion, deux ids).
- e2e manuel : 2 conversations réelles, éditer dans l'une, basculer, revenir,
  vérifier que les éditions et l'état de l'agent sont là ; redémarrer le bridge,
  `resume`, vérifier la persistance.
