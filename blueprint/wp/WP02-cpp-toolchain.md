# WP02 — `cppdev` : toolchain C++ pour l'agent

> **Contexte** : `AgenticEnv` est un **atelier agentique** dont le produit cible est
> le repo C++ `quant-modeling` (bibliothèque de pricing de dérivés : ~26 instruments,
> 8 modèles, moteurs Analytic/MC/PDE/Tree, CMake + vcpkg + Eigen3 + GoogleTest,
> bindings pybind11, CI GitHub Actions).
>
> Un LLM local (llama.cpp, **32K de contexte**) pilote OpenHands, qui exécute le code
> dans une sandbox Docker. Ce work package donne à l'agent les moyens de
> **construire, tester, analyser et mesurer** ce repo C++ de façon fiable.
>
> **Ce package ne contient aucun code de pricing.** Le pricing, c'est le repo cible.

**Fichiers à lire** : ce fichier · [10-TARGET-REPO.md](../10-TARGET-REPO.md) §3 Phase A ·
[03-INTERFACES.md](../03-INTERFACES.md) §6 (contrat MCP) ·
[07-ERRORS-AND-LOGGING.md](../07-ERRORS-AND-LOGGING.md)

**Dépend de** : WP00 (Docker, sandbox), WP01 (`corelib`). **Bloque** : WP08, WP09.

---

## 1. Problème à résoudre

Un agent qui travaille sur un gros projet C++ échoue pour trois raisons récurrentes :

| Problème | Conséquence sans outillage |
|---|---|
| La compilation est lente et les erreurs sont verbeuses | l'agent brûle son contexte de 32K sur des traces de templates |
| Les erreurs C++ sont difficiles à lire | l'agent corrige la mauvaise ligne |
| Les échecs numériques sont silencieux | l'agent « répare » le build en cassant les prix |

L'outillage doit donc : **compiler vite**, **restituer des diagnostics structurés et
tronqués intelligemment**, et **échouer bruyamment sur la numérique**.

---

## 2. Livrables

```text
packages/cppdev/
├── pyproject.toml
├── src/cppdev/
│   ├── schemas.py        # BuildRequest/Report, TestRequest/Report, Diagnostic…
│   ├── errors.py
│   ├── project.py        # découverte du projet : presets, targets, build dir
│   ├── build.py          # configure / build, parsing des diagnostics
│   ├── test.py           # ctest / gtest, parsing des résultats
│   ├── analyze.py        # clang-tidy, cppcheck éventuel
│   ├── sanitize.py       # presets ASan / UBSan / TSan, parsing des rapports
│   ├── coverage.py       # llvm-cov / gcovr
│   ├── bench.py          # exécution + comparaison de benchmarks
│   ├── format.py         # clang-format --dry-run, pre-commit
│   └── diagnostics.py    # normalisation, dédup, troncature, priorisation
└── tests/

packages/cppdev-mcp/
└── src/cppdev_mcp/
    ├── server.py
    ├── schemas.py
    ├── policy.py
    └── tools/{build,test,analyze,sanitize,coverage,bench,format}.py

infra/docker/sandbox/Dockerfile   # étendu : toolchain C++ complète
```

### Toolchain à embarquer dans la sandbox

```text
gcc + clang (les deux : la divergence de diagnostics est un signal)
cmake, ninja, ccache
clangd, clang-tidy, clang-format
lld
gdb
lcov / gcovr / llvm-cov
vcpkg
python3 + pybind11 (pour les bindings du repo cible)
```

---

## 3. Catalogue d'outils MCP

| Outil | Rôle | Timeout |
|---|---|---|
| `cpp.configure` | `cmake --preset <p>`, génère `compile_commands.json` | 300 s |
| `cpp.build` | Build incrémental d'une cible, diagnostics structurés | 900 s |
| `cpp.test` | `ctest` / filtre gtest, résultats structurés | 900 s |
| `cpp.tidy` | `clang-tidy` sur un ensemble de fichiers | 600 s |
| `cpp.format_check` | `clang-format --dry-run` | 60 s |
| `cpp.sanitize` | Build+run sous ASan/UBSan, rapport structuré | 1800 s |
| `cpp.coverage` | Couverture, par fichier et par fonction | 1800 s |
| `cpp.bench` | Exécution de benchmarks + comparaison à une référence | 1800 s |
| `cpp.targets` | Liste des cibles, presets, état du build | 30 s |

---

## 4. Le point critique : la restitution des diagnostics

> C'est la valeur ajoutée principale de ce package. Une erreur de template C++ brute
> fait couramment 200 lignes. Dix erreurs saturent un contexte de 32K.

`diagnostics.py` doit produire :

```jsonc
{
  "ok": false,
  "data": {
    "summary": {"errors": 3, "warnings": 12, "first_error_file": "src/...cpp"},
    "diagnostics": [
      {
        "severity": "error",
        "file": "src/engines/mc/asian.cpp",
        "line": 142, "column": 18,
        "code": "no matching function",
        "message": "<message condensé, 1 à 3 lignes>",
        "template_trace_omitted": 47,
        "related": [{"file": "...", "line": 88, "note": "candidate declared here"}]
      }
    ],
    "truncated_diagnostics": 9
  }
}
```

| Règle de restitution |
|---|
| **La première erreur d'abord.** En C++ les erreurs suivantes sont souvent des conséquences. |
| Les traces d'instanciation de templates sont **repliées** ; leur nombre est indiqué. |
| Les diagnostics identiques répétés sur plusieurs unités de traduction sont **dédupliqués**. |
| Au-delà de N diagnostics (configurable), on tronque et on indique le nombre omis. |
| Les warnings ne noient jamais les erreurs : sections séparées. |
| Le chemin est **relatif au workspace**, jamais absolu host. |
| La sortie brute complète reste accessible via un `log_path` dans `meta`, que l'agent peut lire s'il le demande explicitement. |

**Même traitement pour les tests** : un `ASSERT_NEAR` qui échoue doit remonter
`{test, expected, actual, tolerance, delta}` structuré, pas 40 lignes de sortie gtest.

---

## 5. Build : règles

| # | Règle |
|---|---|
| B1 | **`ccache` activé.** Un agent recompile des dizaines de fois ; sans cache, chaque itération coûte des minutes. |
| B2 | **Ninja** par défaut. |
| B3 | Build **incrémental** par défaut ; `clean` explicite uniquement sur demande. |
| B4 | `compile_commands.json` régénéré à chaque `configure` — c'est la source de WP03. |
| B5 | Presets nommés : `dev` (debug + warnings), `asan`, `ubsan`, `release`, `coverage`, `bench`. |
| B6 | Compilation d'une **cible unique** possible : recompiler tout pour tester un fichier est du gaspillage. |
| B7 | Parallélisme borné par configuration (ne pas saturer la machine qui sert aussi le LLM). |
| B8 | Timeout strict ; un build qui part en boucle est tué et rapporté. |

---

## 6. Tests

| # | Règle |
|---|---|
| T1 | Filtrage gtest supporté (`--gtest_filter`) : exécuter un seul test est la boucle normale d'un agent. |
| T2 | Résultat structuré : nom, statut, durée, message d'assertion **parsé**. |
| T3 | Les tests numériques échoués remontent `expected`/`actual`/`tolerance`. |
| T4 | `cpp.test` ne modifie jamais le code. |
| T5 | Un test qui plante (segfault) est distingué d'un test qui échoue. |
| T6 | La graine et l'environnement sont journalisés : un test MC non déterministe doit être identifiable. |

---

## 7. Sanitizers et analyse statique

> Sur une bibliothèque de pricing avec des noyaux templatés, des accès à des buffers
> de chemins et de l'arithmétique flottante intensive, ASan et UBSan attrapent des
> classes de bugs que les tests ne voient pas.

| Outil | Usage attendu |
|---|---|
| **ASan** | débordements, use-after-free sur les buffers de chemins |
| **UBSan** | comportements indéfinis, notamment conversions et débordements d'entiers dans les index Sobol |
| **clang-tidy** | jeu curé : `bugprone-*`, `performance-*`, `readability-*` sélectionné, `cppcoreguidelines-*` partiel |

`cpp.sanitize` renvoie un rapport structuré : type d'erreur, fichier, ligne, pile
**tronquée aux frames du projet** (les frames système sont repliées).

---

## 8. Benchmarks

Le repo cible a déjà `benchmarks/`. L'outil doit :

- exécuter un sous-ensemble de benchmarks ;
- comparer à une **référence versionnée** ;
- signaler une régression au-delà d'un seuil configurable ;
- rappeler dans `meta` que la machine héberge aussi le LLM ⇒ **les mesures ne sont
  fiables que si `llama-server` est au repos**. L'outil vérifie et avertit sinon.

---

## 9. Intégration sandbox

| Contrainte |
|---|
| Tout s'exécute **dans la sandbox Docker**, jamais sur le host. |
| Le repo est monté sur `/workspace`, utilisateur non-root. |
| Limites CPU/mémoire explicites ; le build ne doit pas affamer `llama-server`. |
| Répertoire de build et cache `ccache` **persistants entre sessions** (volume dédié) — sinon chaque redémarrage repart de zéro. |
| Aucun accès réseau requis après `vcpkg install` initial ; les dépendances sont préinstallées dans l'image. |
| `vcpkg` en mode manifeste, cache binaire monté. |

---

## 10. Tests du package

| Test | Attendu |
|---|---|
| Parsing de diagnostics | corpus figé de sorties gcc et clang → diagnostics structurés attendus |
| Repli des templates | une erreur d'instanciation de 200 lignes produit ≤ 5 lignes + compteur |
| Déduplication | même erreur dans 12 unités de traduction ⇒ 1 diagnostic + compteur |
| Troncature | au-delà du seuil, `truncated_diagnostics` correct, réponse valide |
| Parsing gtest | échec `ASSERT_NEAR` → `expected`/`actual`/`tolerance` extraits |
| Segfault vs échec | distingués |
| Chemins | aucun chemin absolu host dans la sortie |
| Timeout | build en boucle tué et rapporté |
| Idempotence | deux builds successifs sans modification ⇒ second quasi instantané (ccache) |
| Zéro métier | aucune formule financière dans ce package |

---

## 11. Critères d'acceptation

- [ ] `cpp.configure` + `cpp.build` fonctionnent sur `quant-modeling` réel.
- [ ] Une erreur de compilation type produit un diagnostic ≤ 10 lignes exploitable.
- [ ] `cpp.test` exécute un test unique par filtre et renvoie un résultat structuré.
- [ ] Presets `asan` et `ubsan` opérationnels, rapports structurés.
- [ ] `compile_commands.json` généré et consommable par WP03.
- [ ] `ccache` persistant : rebuild incrémental < 10 s sur modification d'un `.cpp`.
- [ ] Couverture et benchmarks exécutables.
- [ ] Aucun chemin host, aucune trace brute non tronquée renvoyée au LLM.
- [ ] `mypy --strict` passe.

---

## 12. Pièges

| Piège | Conduite à tenir |
|---|---|
| Renvoyer la sortie brute du compilateur au LLM | saturation du contexte : toujours passer par `diagnostics.py` |
| Rebuild complet à chaque itération | ccache + build incrémental + cible unique |
| Le build sature la machine et ralentit le LLM | parallélisme borné, limites cgroup |
| Benchmarks lancés pendant que le LLM génère | mesures fausses : l'outil doit avertir |
| L'agent « répare » un test numérique en changeant la tolérance | interdit par la règle R1 de [10-TARGET-REPO.md](../10-TARGET-REPO.md) ; à détecter en revue de diff |
| Divergence gcc/clang ignorée | conserver les deux, une divergence est un signal de code fragile |
