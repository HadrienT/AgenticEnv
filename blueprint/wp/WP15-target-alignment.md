# WP15 — Aligner les outils C++ sur le vrai `quant-modeling`

> **Contexte** : `qmharness` et `codeintel` ont été écrits avant d'avoir le repo cible
> sous la main (marqués `[À CONFIRMER]`). Le repo existe dans `~/quant-modeling`, et les
> hypothèses sont fausses.

**Fichiers à lire** : ce fichier · [WP09](WP09-numerical-harness.md) · [WP03](WP03-code-intelligence.md) ·
[WP02](WP02-cpp-toolchain.md) · [10-TARGET-REPO.md](../10-TARGET-REPO.md) · `quant-modeling/src/module.cpp`

**Dépend de** : — . **Parallélisable avec** : WP11, WP13.

---

## 1. `qmharness` sur la vraie API — #39

**Constat vérifié** : `RealQuantModelingClient` appelle `module.price(...)` et
`module.greeks(...)`. Résultat : `AttributeError`. Le module expose
`price_vanilla_bs_analytic(VanillaBSInput)`, `price_barrier_bs_mc`, etc.
Le seul run en base (`run-store-3`) est un résidu de test.

| Livrable |
|---|
| Table de correspondance `(instrument, model, engine)` vers fonction et type d'entrée du module, générée ou vérifiée au chargement. |
| Lecture réelle du résultat (prix, erreur standard, diagnostics, greeks). |
| `build_dir` corrigé : `build/release` n'existe pas, le build est dans `build/`. Lire le `binaryDir` du preset (`cppdev.project`). |
| Goldens : gardés dans AgenticEnv (`benchmarks/golden`) pour ne pas mêler le harnais au produit, qui tourne en production. |
| Test d'intégration sur le vrai `.so`, ignoré proprement s'il est absent. |

**Acceptation** : `qm.run` en mode `quick` passe sur le vrai module et détecte une
régression injectée.

## 2. Isolation et timeouts — #40

| Constat | Livrable |
|---|---|
| `timeout_s` est ignoré par le client réel | exécution dans un sous-processus tué au timeout |
| Module chargé dans le process MCP : un segfault le tue | même sous-processus, crash rapporté en `fail` |
| `importlib` garde le module en cache : un rebuild n'est pas vu par un serveur longue durée | nouveau sous-processus à chaque run, cohérent avec le `sha256` du fingerprint |

**Acceptation** : test avec une extension factice qui boucle et une qui segfault.

## 3. `codeintel` — #41

| Constat | Livrable |
|---|---|
| `clangd` absent de l'hôte, tous les outils LSP échouent | installation dans `install-stack`, version épinglée, contrôle au healthcheck |
| Tests uniquement sur `FakeClangdClient` | suite d'intégration sur un petit projet C++ réel |
| `registry_matrix` cherche `registerPricer<...>` : 0 occurrence. Le vrai code est `r.register_pricer(key, fn)` dans `src/pricers/registry.cpp` | extraction refaite sur la vraie forme des clés (AST), `configs/codeintel.yaml` corrigé |

**Acceptation** : `code.definition`, `code.references` et `code.registry_matrix` donnent
des résultats exacts sur quant-modeling, vérifiés par un échantillon de pricers.

## 4. `cppdev` — #42

| Constat | Livrable |
|---|---|
| `clang-format`, `clang-tidy` et `gcovr` absents, donc `format_check`, `tidy` et `coverage` inutilisables | installation et healthcheck |
| Pas de `.clang-tidy` dans quant-modeling | config minimale proposée dans ce repo |
| `test`, `sanitize`, `bench` non vérifiés sur le vrai repo | parcours réel documenté, corrections au besoin |

**Acceptation** : les outils `cpp.*` passent sur un vrai projet C++. Sur quant-modeling : `format_check` et `registry_matrix` vérifiés ; `build`, `test`, `coverage` et `sanitize` à repasser par l'opérateur, car ils réécrivent ses dossiers de build.
