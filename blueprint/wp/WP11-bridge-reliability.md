# WP11 — Fiabilité du bridge : tours, annulation, erreurs

> **Contexte** : le bridge traite les messages un par un dans la boucle de lecture
> du socket. Tant qu'un tour tourne, plus rien n'est lu.

**Fichiers à lire** : ce fichier · `packages/openhands-bridge/src/openhands_bridge/server.py` ·
`agenticenv-chat/docs/bridge-v2-spec.md`

**Dépend de** : — (parallélisable avec WP10). **Bloque** : WP08e, WP17.

---

## 1. Sortir le tour de la boucle de lecture — #24

**Constat vérifié** par un test à fausse session : `cancel_turn` envoyé à 0,5 s,
`conversation.pause()` jamais appelé, tour clos par timeout à 10,2 s avec
`reason=error`. La capability `cancel` est annoncée alors qu'elle ne fonctionne pas.
Avec le budget réel (`run.timeout_s: 1800`), l'attente peut durer 30 minutes.

Conséquences à couvrir : `confirm_action` est bloqué de la même façon, et une
déconnexion n'est traitée qu'à la fin du tour, ce qui garde `SESSION_BUSY` (déduit du code).

| Livrable |
|---|
| `_handle_user_message` lancé en `asyncio.Task` attachée à la connexion ; la boucle de lecture reste libre. |
| Un seul tour à la fois : un `user_message` pendant un tour renvoie `TURN_IN_PROGRESS`. |
| À la déconnexion : annuler la tâche, `pause()`, teardown borné, libération du propriétaire. |
| `_sync_to_host` (WP08g) exécuté après annulation, puis `turn_finished` avec `reason=cancelled`. |

**Acceptation** : tests WebSocket à fausse session, sans Docker :
- `pause()` appelé moins de 1 s après `cancel_turn`, `reason=cancelled` ;
- une déconnexion en plein tour libère la session en moins de 20 s, un nouveau
  `start_session` passe ;
- `SESSION_BUSY` ne reste jamais coincé.

## 2. Timeout et erreurs — #25

| Constat | Livrable |
|---|---|
| Au timeout, l'agent n'est pas arrêté (seule une action en attente est rejetée) | `pause()` systématique au timeout |
| Une exception non `AppError` (réseau, `RuntimeError` Docker) sort de la boucle, ferme la connexion et détruit le sandbox | frontière par message : `error` envoyé, session conservée si elle est saine |
| `_emit_post_turn` lit les métriques sans protection, avant `turn_finished` | `turn_finished` garanti dans un `finally` |
| Si `__enter__` échoue après le démarrage du conteneur, `__exit__` n'est pas appelé | `__enter__` nettoie lui-même ce qu'il a créé |

**Acceptation** : tests d'injection de panne sur chaque cas, `turn_finished` toujours
émis, aucun conteneur restant.

## 3. Copie partielle silencieuse — #26

`cp -a /workspace/source/. . 2>/dev/null;` masque les erreurs : le `;` qui suit rend
le code de sortie toujours bon. Un fichier illisible par l'uid 10001 manque sans
avertissement, et l'agent travaille sur un repo incomplet.

| Livrable |
|---|
| Échec de `cp` remonté, avec la liste des fichiers non copiés dans `session_started` ou un `error` dédié. |

**Acceptation** : un fichier en `0600` dans le projet produit un avertissement visible.

## 4. Non-objectifs

Reprise de conversation : WP08e (#10). Streaming : WP17.
