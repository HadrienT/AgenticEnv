# 02 — Repository tree & responsibility map

> ⚠ **Références résiduelles** : les entrées `quantlab`, `quantlab-mcp` et `evalkit`
> sont remplacées par `cppdev`, `codeintel` et `qmharness`. Voir la table de
> substitution dans [README.md](README.md#correctif-de-périmètre--table-de-substitution)
> et les arborescences des WP correspondants.

> Prérequis : [00-PRIMER.md](00-PRIMER.md)

Monorepo unique, géré par `uv` en mode workspace. Racine = ce dépôt.

---

## 1. Arborescence racine

```text
AgenticEnv/
├── README.md
├── pyproject.toml                  # workspace uv : members = packages/*
├── uv.lock
├── justfile                        # tâches: setup, lint, test, migrate, serve, bench
├── .env.example                    # toutes les variables, valeurs factices
├── .gitignore
├── .python-version                 # 3.12
│
├── SYNTHESE-PROJET.md              # vision (non requis pour implémenter)
├── blueprint/                      # ← ce dossier : spécification d'implémentation
│
├── configs/                        # configuration déclarative (versionnée)
├── infra/                          # tout ce qui touche à la machine
├── packages/                       # code Python
├── agents/                         # profils & microagents OpenHands
├── documents/                      # corpus (git-ignoré sauf manifestes)
├── datasets/                       # jeux d'évaluation (git-ignoré sauf manifestes)
├── benchmarks/                     # définitions de benchmarks + résultats
├── migrations/                     # migrations SQL versionnées
├── tests/                          # tests d'intégration et e2e transverses
└── docs/                           # documentation générée / ADR
```

---

## 2. `configs/`

```text
configs/
├── models.yaml                     # registre des modèles LLM + profil actif
├── llama-server.env.j2             # gabarit rendu vers /etc/llm/llama-server.env
├── kbase.yaml                      # chunking, embeddings, retrieval, reranking
├── quantlab.yaml                   # tolérances numériques, seeds, limites MC/PDE
├── agentmem.yaml                   # rétention, seuils de similarité
├── evalkit.yaml                    # suites actives, seuils de passage
├── logging.yaml                    # niveaux, format, destinations
├── mcp/
│   ├── quantlab.yaml               # allowlist d'outils, timeouts, limites
│   ├── kbase.yaml
│   └── agentmem.yaml
└── openhands/
    ├── config.toml.example         # [À CONFIRMER] format exact OpenHands
    └── mcp.json.example            # déclaration des serveurs MCP
```

| Fichier | Responsabilité | Modifié quand |
|---|---|---|
| `models.yaml` | Seule source de vérité du modèle servi et du contexte | changement de modèle ou de `ctx_size` |
| `kbase.yaml` | Tous les hyperparamètres RAG | tuning retrieval |
| `mcp/*.yaml` | Quels outils sont exposés, à quel profil, avec quelles limites | ajout d'un outil |

---

## 3. `infra/`

```text
infra/
├── docker/
│   ├── compose.yaml                # postgres (+ pgadmin optionnel, profil dev)
│   ├── postgres/
│   │   ├── Dockerfile              # base postgres + pgvector
│   │   └── initdb/00-extensions.sql
│   └── sandbox/
│       ├── Dockerfile              # image sandbox agent
│       └── entrypoint.sh
├── systemd/
│   ├── llama-server.service
│   ├── mcp-quantlab.service
│   ├── mcp-kbase.service
│   └── mcp-agentmem.service
└── scripts/
    ├── preflight.sh                # inventaire matériel, aucun effet de bord
    ├── render-llama-env.sh         # configs/models.yaml -> /etc/llm/llama-server.env
    ├── run-llama-server.sh         # wrapper lu par systemd
    ├── healthcheck.sh              # GPU, llama-server, PG, MCP, docker, disque, RAM
    ├── bench-context.sh            # benchmark 8K/16K/32K/64K
    └── gpu-report.sh               # nvidia-smi topo -m + query-gpu -> fichier
```

| Fichier | Responsabilité |
|---|---|
| `preflight.sh` | **Lecture seule.** Vérifie OS, arch, RAM, disque, 2 GPU, compute cap 7.0. Sort non-zéro si un prérequis manque. |
| `render-llama-env.sh` | Traduit le profil actif de `models.yaml` en variables d'environnement. Aucun argument en dur ailleurs. |
| `run-llama-server.sh` | Construit la ligne de commande `llama-server` à partir des variables. Point unique de changement de contexte. |
| `healthcheck.sh` | Code retour 0/1 + sortie JSON. Utilisé par systemd et par les tests e2e. |
| `sandbox/Dockerfile` | Image de dev de l'agent : utilisateur non-root, `/workspace`, toolchain, `quantlab` installé en lecture seule. |

---

## 4. `packages/`

```text
packages/
├── corelib/
│   ├── pyproject.toml
│   ├── src/corelib/
│   │   ├── __init__.py
│   │   ├── config.py          # Settings + chargement YAML/env, validation
│   │   ├── logging.py         # logger structuré JSON, correlation id
│   │   ├── errors.py          # taxonomie d'erreurs racine
│   │   ├── db.py              # engine, session, unit-of-work, healthcheck
│   │   ├── obs.py             # record_tool_invocation, timers, compteurs
│   │   ├── units.py           # validation Rate/Vol/Year/Money, garde-fous
│   │   ├── ids.py             # ULID/UUIDv7, clés déterministes
│   │   ├── hashing.py         # sha256 fichiers/objets, args_sha
│   │   ├── time.py            # horloge injectable, timestamps UTC
│   │   └── serialization.py   # DTO <-> JSON, encodeurs Decimal/Vector
│   └── tests/
│
├── quantlab/
│   ├── pyproject.toml
│   ├── src/quantlab/
│   │   ├── __init__.py
│   │   ├── types.py           # Rate, Vol, Year, Money, Side, OptionType…
│   │   ├── errors.py
│   │   ├── conventions.py     # day count, compounding, business days
│   │   ├── registry.py        # name -> model / method ; matrice de capacités
│   │   ├── repro.py           # construction de l'enregistrement PricingRun
│   │   ├── market/
│   │   │   ├── quote.py       # MarketQuote, VolQuote
│   │   │   ├── curves.py      # DiscountCurve, ForwardCurve
│   │   │   └── surfaces.py    # VolSurface, SliceInterpolator
│   │   ├── instruments/
│   │   │   ├── base.py        # Instrument, Payoff
│   │   │   ├── european.py
│   │   │   ├── american.py
│   │   │   └── forward.py
│   │   ├── models/
│   │   │   ├── base.py        # PricingModel Protocol, ModelParams
│   │   │   ├── black_scholes.py
│   │   │   ├── heston.py
│   │   │   ├── sabr.py
│   │   │   └── local_vol.py
│   │   ├── methods/
│   │   │   ├── base.py        # NumericalMethod Protocol
│   │   │   ├── analytic.py
│   │   │   ├── binomial.py
│   │   │   ├── monte_carlo.py
│   │   │   ├── pde.py
│   │   │   └── fourier.py     # Carr-Madan / COS
│   │   ├── calibration/
│   │   │   ├── base.py        # Calibrator Protocol, CalibrationResult
│   │   │   ├── objective.py
│   │   │   └── optimizers.py
│   │   ├── risk/
│   │   │   ├── greeks.py      # analytiques + bump-and-revalue
│   │   │   └── bumps.py
│   │   ├── rates/
│   │   │   ├── bootstrap.py
│   │   │   └── multicurve.py
│   │   └── validation/
│   │       ├── invariants.py  # parité, bornes, arbitrage, Feller
│   │       └── convergence.py
│   └── tests/
│
├── quantlab-mcp/
│   ├── pyproject.toml
│   └── src/quantlab_mcp/
│       ├── __init__.py
│       ├── server.py          # bootstrap transport stdio | http
│       ├── schemas.py         # JSON Schemas des tools (source de vérité)
│       ├── mapping.py         # DTO JSON <-> types quantlab
│       ├── policy.py          # timeouts, tailles max, allowlist
│       └── tools/
│           ├── pricing.py
│           ├── greeks.py
│           ├── calibration.py
│           ├── curves.py
│           └── validate.py
│
├── kbase/
│   ├── pyproject.toml
│   ├── src/kbase/
│   │   ├── __init__.py
│   │   ├── schemas.py         # Document, ParsedDocument, Section, Chunk, Equation…
│   │   ├── errors.py
│   │   ├── provenance.py      # Citation, formatage, vérification de complétude
│   │   ├── ingestion/
│   │   │   ├── pipeline.py    # orchestration séquentielle idempotente
│   │   │   ├── sources.py     # manifeste local, import fichier
│   │   │   ├── dedup.py       # sha256 + near-dup
│   │   │   ├── structure.py   # reconstruction de l'arbre de sections
│   │   │   ├── equations.py   # extraction/normalisation LaTeX
│   │   │   ├── tables.py
│   │   │   ├── metadata.py    # extraction + normalisation + validité temporelle
│   │   │   ├── chunking.py    # chunking structurel + overlap contrôlé
│   │   │   ├── writer.py      # upsert transactionnel en base
│   │   │   └── parsers/
│   │   │       ├── base.py    # Parser Protocol
│   │   │       ├── pdf.py
│   │   │       └── markdown.py
│   │   ├── embeddings/
│   │   │   ├── base.py        # Embedder Protocol
│   │   │   └── local.py       # modèle local, batching, cache
│   │   ├── retrieval/
│   │   │   ├── query.py       # RetrievalQuery, analyse/expansion
│   │   │   ├── filters.py     # metadata + validité temporelle -> SQL WHERE
│   │   │   ├── vector.py      # VectorIndex (pgvector)
│   │   │   ├── lexical.py     # LexicalIndex (tsvector / FTS)
│   │   │   ├── fusion.py      # RRF
│   │   │   ├── rerank.py      # Reranker Protocol + impl locale
│   │   │   └── hybrid.py      # HybridRetriever — point d'entrée unique
│   │   └── cli.py             # ingest, reindex, search, stats
│   └── tests/
│
├── kbase-mcp/
│   ├── pyproject.toml
│   └── src/kbase_mcp/
│       ├── server.py
│       ├── schemas.py
│       ├── mapping.py
│       ├── policy.py
│       └── tools/
│           ├── search.py
│           ├── get_document.py
│           ├── get_equation.py
│           └── list_topics.py
│
├── agentmem/
│   ├── pyproject.toml
│   ├── src/agentmem/
│   │   ├── schemas.py         # Episode, Procedure, Artifact, Lesson
│   │   ├── errors.py
│   │   ├── episodic.py        # write/search/get
│   │   ├── procedural.py      # load/list/resolve (source = Git)
│   │   ├── search.py          # recherche hybride sur épisodes
│   │   └── cli.py
│   └── tests/
│
├── agentmem-mcp/
│   ├── pyproject.toml
│   └── src/agentmem_mcp/
│       ├── server.py
│       ├── schemas.py
│       └── tools/
│           ├── recall.py
│           ├── remember.py
│           └── procedures.py
│
└── evalkit/
    ├── pyproject.toml
    ├── src/evalkit/
    │   ├── schemas.py         # BenchmarkItem, EvalRun, EvalResult
    │   ├── suites/
    │   │   ├── base.py        # Suite Protocol + loader
    │   │   ├── external.py    # adaptateurs datasets publics
    │   │   └── internal.py    # benchmark maison 300 questions
    │   ├── runners/
    │   │   ├── base.py
    │   │   ├── retrieval.py   # évalue kbase seul
    │   │   ├── numeric.py     # évalue quantlab seul
    │   │   └── agent.py       # évalue le système complet via OpenHands
    │   ├── judges/
    │   │   ├── numeric.py     # tolérance absolue/relative
    │   │   ├── citation.py    # la citation justifie-t-elle l'affirmation
    │   │   └── llm.py         # LLM-as-judge (optionnel, désactivable)
    │   ├── metrics/
    │   │   ├── retrieval.py   # recall@k, precision, MRR, NDCG
    │   │   ├── numeric.py     # erreurs prix/greeks/calibration/convergence
    │   │   └── agent.py       # tool selection, self-correction, error handling
    │   ├── report.py          # markdown + JSON
    │   └── cli.py
    └── tests/
```

---

## 5. `agents/`

```text
agents/
├── profiles/
│   ├── orchestrator.yaml       # profil par défaut, plan + délégation
│   ├── research.yaml           # lecture seule + kbase.*
│   ├── quant.yaml              # quantlab.* + kbase.search
│   ├── coding.yaml             # fs/terminal/git + quantlab.*
│   └── validation.yaml         # quantlab.validate + pytest
├── microagents/                # [À CONFIRMER] format OpenHands (.openhands/microagents)
│   ├── repo.md                 # connaissance du repo, toujours chargée
│   ├── quant-conventions.md    # unités, conventions, interdits numériques
│   ├── rag-citation.md         # comment citer, séparation Source/Raisonnement/Calcul
│   └── git-checkpoint.md       # discipline de branche et de commit
└── prompts/
    ├── system-common.md        # socle commun à tous les profils
    └── snippets/
```

Un `profiles/*.yaml` déclare : `role`, `system_prompt`, `mcp_tools` (allowlist),
`permissions`, `limits`. Voir [06-CONFIG.md](06-CONFIG.md) §5.

---

## 6. `migrations/`, `documents/`, `datasets/`, `benchmarks/`, `tests/`, `docs/`

```text
migrations/
├── 0001_extensions.sql          # vector, pg_trgm, unaccent
├── 0002_schema_kb.sql
├── 0003_schema_mem.sql
├── 0004_schema_eval.sql
├── 0005_schema_obs.sql
├── 0006_schema_quant.sql
└── README.md                    # ordre, politique d'irreversibilité

documents/
├── manifest.yaml                # source de vérité du corpus (versionnée)
├── raw/                         # git-ignoré
├── parsed/                      # git-ignoré
└── processed/                   # git-ignoré

datasets/
├── manifest.yaml                # datasets externes : nom, version, licence, checksum
└── cache/                       # git-ignoré

benchmarks/
├── internal/
│   ├── theory.yaml              # 100 questions
│   ├── pricing.yaml             # 100 questions
│   └── numerics.yaml            # 100 questions
├── golden/
│   └── reference_prices.yaml    # valeurs de référence quant
└── results/                     # git-ignoré

tests/
├── integration/
│   ├── test_db_schema.py
│   ├── test_ingestion_roundtrip.py
│   ├── test_retrieval_quality.py
│   └── test_mcp_contracts.py
├── e2e/
│   ├── test_llama_server.py
│   ├── test_openhands_reaches_llm.py
│   └── test_agent_smoke.py
└── conftest.py

docs/
├── adr/                         # une décision = un fichier, immuable
├── runbook.md                   # démarrage, arrêt, incidents
└── limitations.md               # limites connues
```

---

## 7. Responsibility map — vue synthétique

| Question | Fichier unique de réponse |
|---|---|
| Quel modèle est servi, avec quel contexte ? | `configs/models.yaml` |
| Comment le serveur LLM est lancé ? | `infra/scripts/run-llama-server.sh` |
| Quelles variables de config existent ? | `packages/corelib/src/corelib/config.py` + `.env.example` |
| Quelles erreurs peuvent être levées ? | `packages/corelib/src/corelib/errors.py` |
| Quel est le schéma de la base ? | `migrations/*.sql` + [04-DATA-MODEL.md](04-DATA-MODEL.md) |
| Quels outils sont exposés au LLM ? | `configs/mcp/*.yaml` + `packages/*-mcp/src/*/schemas.py` |
| Quels couples (modèle, méthode) sont supportés ? | `packages/quantlab/src/quantlab/registry.py` |
| Quels hyperparamètres RAG ? | `configs/kbase.yaml` |
| Quelles valeurs de référence numériques ? | `benchmarks/golden/reference_prices.yaml` |
| Quel agent a le droit de faire quoi ? | `agents/profiles/*.yaml` |
