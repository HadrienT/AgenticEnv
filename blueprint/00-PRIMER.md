# 00 — PRIMER (à lire par tout agent, sans exception)

> Ce fichier est le **contexte minimal complet**. Vous n'avez pas besoin de lire
> `SYNTHESE-PROJET.md`. Durée de lecture : ~4 minutes.

---

## 1. Ce qu'on construit

**Deux choses distinctes, à ne jamais confondre :**

| | Quoi | Où |
|---|---|---|
| **Le produit** | `quant-modeling` — bibliothèque **C++** de pricing et de risk management de produits dérivés | https://github.com/HadrienT/quant-modeling |
| **L'atelier** | `AgenticEnv` — environnement agentique local qui aide à construire le produit | ce repo |

L'atelier est un **moyen**. L'objectif est le code C++ : vérifier ce qui existe,
ajouter des produits, introduire les conventions de temps et les échéanciers,
implémenter l'AAD. Voir [10-TARGET-REPO.md](10-TARGET-REPO.md).

On ne construit **pas** un chatbot, ni un moteur de pricing en Python.

## 2. Les 3 principes non négociables

**(P1) Le LLM n'est pas le moteur de vérité numérique.**
Tout calcul financier est fait par du code déterministe — en l'occurrence la
bibliothèque C++. Le LLM écrit du code et appelle des outils ; il ne calcule pas.

**(P2) Le raisonnement est séparé de l'exécution.**
`LLM → décision structurée → harness → validation → exécution → résultat → LLM`.
Les permissions sont appliquées au **runtime**, jamais via le prompt.

**(P3) Le système trouve, calcule, teste et vérifie — il ne mémorise pas.**
La connaissance vient du RAG, pas des poids du modèle.

## 3. Ce qu'on ne construit PAS

Le **harness est OpenHands**. Décision verrouillée. On n'écrit pas d'agent loop,
pas de tool executor, pas de state manager, pas d'orchestrateur multi-agent
maison. Tout cela existe déjà dans OpenHands.

On n'écrit **pas non plus de moteur de pricing** : il existe déjà en C++, avec
~26 instruments, 8 modèles, moteurs Analytic/MC/PDE/Tree, Sobol RQMC, pont brownien,
Monte Carlo conditionnel et des bindings pybind11. Le réimplémenter en Python serait
un doublon inférieur et une seconde source de vérité — le pire résultat possible.

Ce que **nous** écrivons :

1. `corelib` — noyau partagé (config, logging, erreurs, accès DB, unités).
2. `cppdev` — toolchain C++ : build, tests, sanitizers, **diagnostics condensés**.
3. `codeintel` — intelligence de code C++ (clangd) : naviguer un gros repo sans saturer 32K.
4. `kbase` — pipeline documentaire + recherche hybride (RAG).
5. `agentmem` — mémoire épisodique et procédurale.
6. `qmharness` — non-régression numérique, pilotant la **bibliothèque C++ existante**.
7. Des **serveurs MCP** exposant 2 à 6 à OpenHands.
8. L'**infrastructure** (llama.cpp, systemd, Docker, PostgreSQL, image sandbox).

## 4. Décisions verrouillées (ne pas rediscuter)

| Sujet | Décision |
|---|---|
| OS | Debian 13 amd64, headless |
| GPU | 2 × Tesla V100 16 GiB (Volta, compute capability **7.0**) |
| Driver NVIDIA | **propriétaire** — jamais `nvidia-open` (Volta non supporté) |
| CUDA | **12.x** — **jamais CUDA 13** (support Volta supprimé) |
| Moteur d'inférence | **llama.cpp / `llama-server`** — pas vLLM, pas Ollama |
| Multi-GPU | `--split-mode layer`, layers répartis sur les 2 GPU |
| Budget modèle | **≤ 20 GiB de poids** (GGUF quantifié), 100 % en VRAM |
| Offload CPU | **aucun**, jamais, sous aucun prétexte |
| Contexte | **32768 tokens** par défaut, **changeable par configuration** |
| Modularité modèle | tout modèle GGUF doit être pluggable via un **registre de modèles** en config, sans changer de code |
| Harness / runtime agent | **OpenHands** |
| Sandbox | **Docker**, jamais le mode Process pour l'autonome |
| API LLM | OpenAI-compatible, `127.0.0.1:8000` |
| Stockage connaissance | **PostgreSQL + pgvector + Full Text Search**. Pas de Qdrant, pas d'OpenSearch |
| Recherche | hybride : vector + FTS/BM25 + filtres metadata + reranker |
| Checkpoints | Git — 1 tâche = 1 branche, 1 étape majeure = 1 commit |
| RAM / SSD | **non contraints** (le matériel sera étendu si besoin) |
| Adaptation modèle | RAG d'abord. Fine-tuning/LoRA = phase finale, comportement uniquement |
| Langage (atelier) | Python 3.12+, typé, `uv` pour la gestion des dépendances |
| Langage (produit) | C++ (CMake + vcpkg + Eigen3 + GoogleTest), bindings pybind11 |

## 5. Interdits absolus

1. Installer CUDA 13 ou les NVIDIA open kernel modules.
2. Faire de l'offload CPU des poids du modèle.
3. Démarrer le modèle à 256K de contexte.
4. Exposer `llama-server`, PostgreSQL ou un serveur MCP sur `0.0.0.0` sans demande explicite.
5. Monter `/`, `/etc`, `/home`, `~/.ssh` ou des credentials dans la sandbox.
6. Masquer une erreur avec `|| true`, un `except: pass` ou un fallback silencieux.
7. **Réimplémenter du pricing hors du repo C++.**
8. **Modifier une valeur de référence numérique sans justification et validation humaine.**
9. Renvoyer au LLM une sortie brute de compilateur ou un fichier source entier.
10. Coder une valeur de configuration en dur (chemin, port, taille de contexte, nom de modèle).
11. Ajouter une dépendance à un framework agentique (LangChain, LlamaIndex, CrewAI…).
12. Introduire du multi-agent, un knowledge graph ou du fine-tuning avant que le socle soit validé.
13. Écrire directement sur la branche `main` depuis un agent autonome.
14. Deviner une API tierce. Les points `[À CONFIRMER]` se vérifient dans la doc officielle.

## 6. Vocabulaire

| Terme | Sens dans ce projet |
|---|---|
| **Le produit** | le repo C++ `quant-modeling`. Ce qu'on construit. |
| **L'atelier** | ce repo `AgenticEnv`. Comment on le construit. |
| **Harness** | OpenHands. La boucle agentique, l'exécution des outils, l'état, la sandbox. |
| **Tool** | Une capacité exposée au LLM. Ici : via MCP. |
| **MCP server** | Adaptateur **fin** entre OpenHands et une de nos bibliothèques. Zéro logique métier. |
| **Chunk** | Unité de texte indexée dans le RAG, avec metadata et provenance. |
| **Provenance** | document + auteur + année + page + section + équation + hash + source. Obligatoire. |
| **Episode** | Trace d'une tâche passée : objectif, actions, résultat, leçon. |
| **Procédure** | Recette réutilisable (« comment migrer un instrument vers les dates »), versionnée dans Git. |
| **Valeur de référence** | Prix figé, vérifié contre une source externe. Le déplacer exige une justification. |

## 7. Conventions critiques (détail dans `09-CONVENTIONS.md`)

- **Unités explicites, toujours** : `rate=0.03` (jamais `3`), `vol=0.20` (jamais `20`), `maturity_years=1.0`.
- Tout résultat de pricing est **reproductible** : modèle, version, méthode, paramètres, seed, tolérance, commit.
- Toute affirmation issue du RAG porte sa **citation**.
- Trois catégories d'énoncés à ne jamais mélanger : **Source** / **Raisonnement** / **Résultat calculé**.

## 8. Definition of Done (minimum, pour toute contribution)

- [ ] Signatures typées, `mypy --strict` passe.
- [ ] Tests unitaires + tests de contrat sur les schémas publics.
- [ ] Aucune valeur de config en dur.
- [ ] Erreurs issues de la taxonomie de `07-ERRORS-AND-LOGGING.md`.
- [ ] Logging structuré aux frontières du composant.
- [ ] Docstring d'une ligne sur les fonctions publiques uniquement.
- [ ] Aucun secret dans le code ni dans les logs.
