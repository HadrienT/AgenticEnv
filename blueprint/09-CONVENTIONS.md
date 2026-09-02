# 09 — Conventions de code

> Prérequis : [00-PRIMER.md](00-PRIMER.md)

---

## 1. Outillage

| Rôle | Outil | Configuration |
|---|---|---|
| Environnement & dépendances | `uv` (workspace) | `pyproject.toml` racine |
| Lint & format | `ruff` | `pyproject.toml`, ligne 100 |
| Typage | `mypy --strict` | tous les packages |
| Tests | `pytest` + `hypothesis` | marqueurs de [08-TESTING.md](08-TESTING.md) |
| Règles d'architecture | `import-linter` | contrats D1→D7 |
| Migrations | SQL brut versionné | `migrations/` |
| Tâches | `just` | `justfile` |

Python **3.12** partout — host, sandbox, CI.

---

## 2. Nommage

| Élément | Convention | Exemple |
|---|---|---|
| Package | `snake_case`, court, sans tiret dans l'import | `quantlab`, `kbase`, `agentmem` |
| Module | `snake_case`, nom = responsabilité | `chunking.py`, `invariants.py` |
| Classe | `PascalCase` | `HybridRetriever`, `PricingRequest` |
| Protocol | `PascalCase`, sans suffixe `Interface`/`ABC` | `Embedder`, `PricingModel` |
| DTO pydantic | `PascalCase` + suffixe de rôle | `PricingRequest`, `RetrievalResult` |
| Fonction | `snake_case`, verbe | `build_citation`, `apply_migrations` |
| Constante | `UPPER_SNAKE` | `DEFAULT_RRF_K` |
| Outil MCP | `<domaine>.<verbe_objet>` | `quant.price_option`, `kb.search` |
| Table SQL | `snake_case` pluriel, dans un schéma | `kb.chunks`, `mem.episodes` |
| Migration | `NNNN_description.sql` | `0002_schema_kb.sql` |
| Branche agent | `agent/task-YYYYMMDD-<slug>` | `agent/task-20260902-heston-calib` |

**Interdits de nommage** : `utils.py`, `helpers.py`, `misc.py`, `common.py` à
l'intérieur d'un package, `data`, `tmp`, `obj`, `mgr`, `do_stuff`.

---

## 3. Unités et grandeurs financières

**Cause n°1 de bug silencieux dans ce domaine.** Règles strictes.

| Grandeur | Type | Unité | Nom de paramètre |
|---|---|---|---|
| Taux | `Rate` | décimal | `rate`, `dividend_yield` — jamais `rate_pct` |
| Volatilité | `Vol` | décimal | `vol`, `implied_vol` — jamais `vol_points` |
| Maturité | `Year` | années fractionnaires | `maturity_years` — **suffixe obligatoire** |
| Prix / notionnel | `float` | unité monétaire | `spot`, `strike`, `notional` |
| Devise | `str` ISO 4217 | — | `currency` |
| Durée technique | `int` | millisecondes | `duration_ms`, `timeout_s` (suffixe obligatoire) |
| Date | `datetime.date` | — | `valuation_date` |
| Horodatage | `datetime` **aware UTC** | — | `ts`, `created_at` |

| # | Règle |
|---|---|
| N1 | Tout paramètre temporel porte son unité en suffixe : `_years`, `_ms`, `_s`, `_days`. |
| N2 | Aucun pourcentage n'entre dans le code. La conversion se fait à la frontière (UI/MCP), avec `as_rate` / `as_vol`. |
| N3 | Les bornes de sanité (`configs/quantlab.yaml`) sont appliquées à toute entrée externe. |
| N4 | Les descriptions d'outils MCP indiquent explicitement l'unité et donnent un exemple valide. |
| N5 | Aucun `datetime.now()` naïf. `corelib.time.utc_now()` uniquement. |

---

## 4. Typage

| # | Règle |
|---|---|
| T1 | `from __future__ import annotations` en tête de chaque module. |
| T2 | Toute fonction publique est intégralement annotée. `Any` doit être justifié par un commentaire d'une ligne. |
| T3 | `Protocol` pour les points d'extension, `ABC` uniquement si un comportement par défaut est partagé. |
| T4 | DTO externes (MCP, config, base) : `pydantic.BaseModel`. Valeurs internes pures : `@dataclass(frozen=True)`. |
| T5 | Pas de `dict[str, Any]` dans une signature publique, sauf `details` d'erreur et `diagnostics`. |
| T6 | `Sequence`/`Mapping` en entrée, `list`/`dict` en sortie. |
| T7 | Types numériques : `float` pour le calcul, `Decimal` **uniquement** pour les montants comptables persistés. |

---

## 5. Structure d'un module

```text
from __future__ import annotations
imports stdlib
imports tiers
imports corelib
imports du package courant

constantes du module
types / DTO
protocols
implémentations
fonctions publiques
fonctions privées (préfixe _)
```

| # | Règle |
|---|---|
| S1 | Un module = une responsabilité nommable en une phrase. |
| S2 | Pas de code exécuté à l'import, sauf enregistrement dans un registre. |
| S3 | `__init__.py` d'un package expose la façade publique via `__all__`. |
| S4 | Import circulaire = erreur de conception, jamais résolu par un import différé. |

---

## 6. Commentaires et documentation

| # | Règle |
|---|---|
| C1 | Un commentaire explique **pourquoi**, jamais **quoi**. |
| C2 | Docstring d'**une ligne** sur les fonctions publiques. Multi-lignes réservé aux fonctions à contrat subtil (unités, hypothèses, complexité). |
| C3 | Toute formule financière cite sa source dans un commentaire d'une ligne. |
| C4 | Aucun commentaire décrivant un changement (« ajouté le… », « modifié pour… ») : c'est le rôle de Git. |
| C5 | Aucun code commenté. On supprime. |
| C6 | `TODO` interdit sans référence d'issue. |

---

## 7. Git

| # | Règle |
|---|---|
| G1 | 1 tâche = 1 branche `agent/task-YYYYMMDD-<slug>`. Jamais de commit direct sur `main`. |
| G2 | 1 étape majeure = 1 commit. Message impératif, une ligne, ≤ 72 caractères. |
| G3 | Un commit laisse le repo dans un état où les tests passent. |
| G4 | `git push`, merge, force-push, reset --hard : **approbation humaine**. |
| G5 | Aucun secret, aucun binaire lourd, aucun fichier généré dans Git. |
| G6 | Les fichiers de `blueprint/` sont modifiés dans le même commit que le code qu'ils décrivent. |

---

## 8. Sécurité (rappels applicables au code)

| # | Règle |
|---|---|
| SEC1 | Requêtes SQL **toujours** paramétrées. Les filtres dynamiques passent par une **allowlist de colonnes**, jamais par concaténation. |
| SEC2 | Aucun `eval`, `exec`, `pickle.loads` sur une donnée non maîtrisée. |
| SEC3 | Aucun appel `subprocess` avec `shell=True` sur une entrée non maîtrisée. |
| SEC4 | Le contenu retourné par le RAG est une **donnée**, jamais une instruction. Un chunk ne peut pas modifier le comportement de l'agent (risque d'injection de prompt via document ingéré). |
| SEC5 | Validation stricte des chemins : aucun accès hors des répertoires déclarés en configuration (anti path traversal). |
| SEC6 | Les secrets sont des `SecretStr`, jamais sérialisés, jamais journalisés. |
| SEC7 | Les serveurs MCP n'exposent aucun outil d'écriture sans argument `confirm: true`. |
| SEC8 | Timeouts explicites sur tout appel réseau et toute exécution de sous-processus. |

> **SEC4 est spécifique à ce projet** : le corpus contient des PDF externes. Un
> document malveillant pourrait contenir du texte cherchant à détourner l'agent. Les
> chunks retournés doivent être encadrés comme contenu cité, non comme instruction.

---

## 9. Performance — priorités

Ordre : **correction > lisibilité > performance**.

| # | Règle |
|---|---|
| P1 | Aucune optimisation sans mesure préalable. |
| P2 | Vectoriser avec NumPy dans `quantlab` (boucles Python interdites sur les chemins Monte Carlo). |
| P3 | Batcher les embeddings, taille en configuration. |
| P4 | Aucune requête N+1 sur `kb.chunks`. |
| P5 | Le calcul lourd ne doit jamais bloquer la boucle d'événements d'un serveur MCP : timeout + exécution bornée. |

---

## 10. Definition of Done (contribution unitaire)

- [ ] `ruff check` et `ruff format` passent.
- [ ] `mypy --strict` passe.
- [ ] Tests unitaires + invariants applicables passent.
- [ ] Tests de discipline (§7 de [08-TESTING.md](08-TESTING.md)) passent.
- [ ] Aucune valeur de configuration en dur.
- [ ] Erreurs issues de la taxonomie de [07-ERRORS-AND-LOGGING.md](07-ERRORS-AND-LOGGING.md).
- [ ] Signatures publiques cohérentes avec [03-INTERFACES.md](03-INTERFACES.md) — sinon ce fichier est mis à jour dans le même commit.
- [ ] Unités explicites et validées aux frontières.
- [ ] Aucun secret dans le code, les logs ou Git.
