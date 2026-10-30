# WP14 — Rendre `agentmem` utile

> **Contexte** : le code est propre, mais la mémoire est vide (0 épisode, 1 procédure
> illustrative) et utilise un embedder factice. Rien n'écrit dedans.

**Fichiers à lire** : ce fichier · [WP07](WP07-agentmem.md) · `packages/agentmem/src/agentmem/`

**Dépend de** : WP12 (accès MCP), WP13 §2 (embedder). 

---

## 1. Embedder réel — #36

| Livrable |
|---|
| Même serveur d'embeddings que WP13, par une interface locale à `agentmem` (le contrat import-linter D10 interdit `agentmem -> kbase`). |
| Fabrique lue depuis `configs/agentmem.yaml`, migration `vector(D)`, `min_similarity` recalibré sur des données réelles. |

## 2. Capture et rappel automatiques — #37

| Livrable |
|---|
| Le bridge produit un épisode en fin de session : objectif, résumé LLM, leçons, fichiers touchés, statut. Pas de dépendance à la bonne volonté de l'agent. |
| `mem.recall` injecté dans le contexte au premier message, avec un budget de tokens. |
| `mem.remember` reste disponible à l'agent. Rédaction des secrets conservée. |
| Oubli : suppression à la demande, et commande pour lister. |

**Acceptation** : deux sessions successives sur le même sujet, la seconde cite la
leçon de la première. Aucun épisode ne contient de secret sur le jeu de test.

## 3. Procédures réelles — #38

| Livrable |
|---|
| Remplacer `calibrate-sabr.yaml` illustratif par 3 à 5 procédures validées sur quant-modeling (ajout d'un pricer, calibration, investigation d'une régression). |
