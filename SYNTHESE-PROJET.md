# Synthèse projet — Plateforme d'agents IA locale pour le quant / pricing de dérivés

> Document de synthèse consolidant :
> - `LOCAL_LLM_AGENT_SERVER_SETUP.md` (infrastructure serveur)
> - `Spécification — Plateforme d'Agent IA avec Harness.md` (plateforme d'exécution d'agents)
> - `Architecture d'une CDLLM locale pour le pricing de produits dérivés.md` (domaine quant + connaissance)
> - `Rag dataset.md` (dataset d'évaluation RAG finance)
>
> Aucune information n'est ajoutée par rapport aux sources. Les divergences entre documents sont explicitement signalées en §7.

---

# 1. Vue d'ensemble & objectifs

## 1.1 Objectif final

Construire une **plateforme locale d'agents IA autonomes**, entièrement auto-hébergée, capable de :

- recevoir un objectif ;
- analyser son environnement ;
- utiliser des outils (filesystem, terminal, git, tests, build, MCP) ;
- écrire et exécuter du code dans une sandbox Docker ;
- vérifier ses résultats et itérer jusqu'à l'objectif ou une condition d'arrêt.

Le cas d'usage cible est la construction progressive d'un **logiciel de pricing et de risk management de produits dérivés**.

## 1.2 Les trois couches du projet

```text
Couche 3 — DOMAINE QUANT
  RAG financier, Quant Engine, agents spécialisés, mémoire, évaluation

Couche 2 — PLATEFORME AGENTIQUE (Harness)
  Agent Loop, Context, Tools, State, Permissions, Guardrails, Observability

Couche 1 — INFRASTRUCTURE
  Debian 13 + driver NVIDIA + CUDA 12.x + llama.cpp + Docker + OpenHands
```

## 1.3 Principes directeurs

Trois principes structurent tout le projet.

**(a) Le LLM n'est pas le moteur de vérité numérique.**

> Il est le cerveau qui raisonne, recherche, orchestre et utilise des outils spécialisés.

**(b) Le raisonnement est séparé de l'exécution.**

```text
LLM → décision structurée → Harness → validation → exécution → résultat → LLM
```

**(c) Le système doit trouver, calculer, tester et vérifier — pas mémoriser.**

> *Don't make the model know everything. Make the system able to find, calculate, test and verify everything it needs.*

Le modèle doit savoir : ce qu'il cherche, où chercher, quel outil utiliser, comment interpréter le résultat, comment le vérifier, comment conserver l'expérience.

## 1.4 Quatre choses à ne jamais confondre

| Élément | Rôle | Support |
|---|---|---|
| **Le modèle** | raisonnement, planning, sélection d'outils, écriture de code | Qwen local |
| **La connaissance** | faits, papers, équations, conventions | RAG / Knowledge Base |
| **Les outils** | calculs déterministes, actions | Quant Engine, tools, sandbox |
| **La mémoire** | continuité, expériences, procédures | Working / Episodic / Semantic / Procedural |

---

# 2. Architecture globale

## 2.1 Architecture infrastructure (couche 1)

```text
                    ┌───────────────────────┐
                    │       VS Code         │
                    │ Copilot / ACP / GUI   │
                    └───────────┬───────────┘
                                ▼
                    ┌───────────────────────┐
                    │   OpenHands / Agent   │
                    └───────────┬───────────┘
                                │  OpenAI-compatible HTTP
                                ▼
                    ┌───────────────────────┐
                    │      llama.cpp        │
                    │     llama-server      │
                    └───────────┬───────────┘
                                ▼
                         2 × V100 16 GiB
                                ▼
                    Qwen3-Coder-30B-A3B (GGUF Q4)

Agent tools : filesystem, terminal, git, tests, build,
              Docker sandbox, MCP servers, GitHub
```

Séparation stricte des responsabilités :

| Composant | Responsabilité |
|---|---|
| NVIDIA driver | accès matériel GPU |
| CUDA 12.x | compilation/runtime GPU pour llama.cpp |
| llama.cpp | sert uniquement le modèle |
| OpenHands | boucle agentique, outils, interface, sandbox |
| Docker | isolation de l'exécution du code |
| MCP | protocole standard pour outils/services additionnels |
| Git | checkpoints et rollback |
| systemd | démarrage automatique des services |
| VS Code | interface de développement (pas le cœur de l'infra) |

## 2.2 Architecture plateforme / Harness (couche 2)

```text
                             USER
                               ▼
                    ┌──────────────────────┐
                    │  APPLICATION / API   │
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │   AGENT CONTROLLER   │
                    │  Goal / Task / State │
                    └──────────┬───────────┘
                               ▼
         ┌───────────────────────────────────────────┐
         │                 HARNESS                    │
         │  ┌─────────────────────────────────────┐  │
         │  │            AGENT LOOP               │  │
         │  │  Observe → Reason → Act → Verify    │  │
         │  │       ↑                    │        │  │
         │  │       └────────────────────┘        │  │
         │  └──────────────────┬──────────────────┘  │
         │       ┌─────────────┼──────────────┐      │
         │       ▼             ▼              ▼      │
         │    Context        Tools          Memory   │
         │       │             │              │      │
         │       ▼             ▼              ▼      │
         │  RAG/Retrieval  Tool Runtime    Storage   │
         │                     ▼                     │
         │                Environment                │
         │                                           │
         │  Guardrails / Permissions / Limits        │
         │  State / Retry / Logging / Evaluation     │
         └────────────────────┬──────────────────────┘
                              ▼
                    ┌─────────────────┐
                    │       LLM       │
                    │ Reasoning       │
                    │ Planning        │
                    │ Tool selection  │
                    └─────────────────┘
```

Contenu du Harness :

```text
Harness
├── Agent Loop            ├── Guardrails
├── Context Builder       ├── Retry Manager
├── Tool Registry         ├── Evaluator
├── Tool Executor         ├── Observability
├── State Manager         ├── Cost Manager
├── Memory Manager        ├── Timeout Manager
├── Permission Manager    └── Persistence
```

## 2.3 Architecture domaine quant (couche 3)

```text
                         ┌───────────────────────┐
                         │       QWEN LLM        │
                         │ reasoning / planning  │
                         │ orchestration         │
                         └───────────┬───────────┘
                ┌────────────────────┼────────────────────┐
                ▼                    ▼                    ▼
        Knowledge Engine        Quant Engine        Agent Sandbox
                │                    │                    │
        ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
        │ RAG          │      │ Pricing      │      │ Python/C++   │
        │ Vector DB    │      │ Calibration  │      │ Code         │
        │ BM25         │      │ Greeks       │      │ Tests        │
        │ Knowledge    │      │ Monte Carlo  │      │ Experiments  │
        │ Graph        │      │ PDE / FFT    │      │ Compilation  │
        └──────────────┘      └──────────────┘      └──────────────┘
                └────────────────────┼────────────────────┘
                                     ▼
                              Validation Engine
                                     ▼
                                Final Result
```

Multi-agent cible (à n'introduire qu'en phase tardive) :

```text
                    Orchestrator
                         │
      ┌──────────────────┼──────────────────┐
      ▼                  ▼                  ▼
Research Agent      Quant Agent       Coding Agent
      ▼                  ▼                  ▼
   RAG DB          Quant Library         Sandbox
      └──────────────────┼──────────────────┘
                         ▼
                  Validation Agent
                         ▼
                  Final Response
```

| Agent | Responsabilité |
|---|---|
| **Orchestrator** | quels agents, dans quel ordre, quels outils, quand valider, quand s'arrêter |
| **Research** | recherche RAG, papers pertinents, hypothèses, équations, contradictions entre sources |
| **Quant** | choix du modèle, hypothèses, méthode numérique, calibration, paramètres, tests |
| **Coding** | écrit/compile/exécute/corrige le code en sandbox, benchmark |
| **Validation** | cohérence math & dimensionnelle, convergence, arbitrage, limites asymptotiques, comparaison à des références, stabilité numérique, qualité des sources |

## 2.4 Chaîne de responsabilité anti-hallucination

```text
LLM        → "Que dois-je faire ?"
Agent      → "Quel outil dois-je utiliser ?"
Tool       → "Voici le résultat."
Validator  → "Le résultat est-il correct ?"
LLM        → "Voici l'explication."
```

---

# 3. Choix techniques & justifications (trade-offs)

## 3.1 Tableau récapitulatif des décisions

| Sujet | Choix | Justification / trade-off |
|---|---|---|
| OS | Debian 13 amd64, headless | configuration cible connue |
| GPU | 2 × Tesla V100 16 GiB (Volta, CC 7.0) | matériel existant |
| Driver | NVIDIA **propriétaire** | les *open kernel modules* ne supportent pas Volta |
| CUDA | **12.x** (12.8 / 12.9 selon driver) | CUDA 13 a supprimé la compilation offline et le support des libs pour Volta |
| Serveur d'inférence | **llama.cpp / llama-server** | contrôle précis du multi-GPU, du contexte et des paramètres CUDA ; Ollama écarté comme composant principal |
| Multi-GPU | `--split-mode layer` | mode par défaut/recommandé ; `tensor` est expérimental et dépend fortement de l'interconnexion |
| Modèle | Qwen3-Coder-30B-A3B-Instruct (GGUF) | MoE 30.5B / ~3.3B activés, contexte natif 262144, conçu pour le coding agentique et les function calls |
| Quantification | **Q4 / UD-Q4** au premier déploiement | Q5/Q6 laissent trop peu de VRAM pour le KV cache et les buffers ; BF16 impossible |
| Contexte initial | **32K** | ne pas démarrer à 256K : le support natif ≠ VRAM disponible |
| Offload | **aucun** | règle absolue : ne jamais dégrader vers CPU/offload pour « faire marcher » quelque chose |
| Agent runtime | OpenHands (CLI via `uv`, Python 3.12+) | GUI local sur `http://localhost:3000`, parle LiteLLM/OpenAI-compatible |
| Sandbox | **Docker sandbox** obligatoire | ne pas utiliser le mode Process pour des tâches autonomes ou non fiables |
| Persistance / checkpoints | Git (1 tâche = 1 branche, 1 étape majeure = 1 commit) | rollback, jamais d'écriture directe sur `main` |
| Démarrage services | systemd (`llama-server.service`, user système `llm`) | redémarrage automatique après reboot |
| Réseau | `127.0.0.1` par défaut, accès distant via tunnel SSH | ne pas exposer le LLM ni MCP sans auth + reverse proxy |
| Stockage connaissance (v1) | PostgreSQL + pgvector + Full Text Search | suffisant au début ; inutile de déployer 15 bases |
| Stockage connaissance (v2) | PostgreSQL + Qdrant + OpenSearch | structuré / vectoriel / lexical spécialisés |
| Recherche | hybride **vector + BM25 + metadata filtering + reranker** | la recherche purement vectorielle échoue sur des termes très lexicaux (κ, θ, σ, ρ, Feller, CVA, PFE, SOFR, SABR) |
| Adaptation modèle | **RAG d'abord, fine-tuning en dernier** | RAG = connaissance ; fine-tuning/LoRA = comportement. Le fine-tuning ne remplace pas une base documentaire |
| Framework agentique | éviter la dépendance forte à un framework | les APIs internes doivent rester stables |

## 3.2 Répartition GPU — à benchmarker

```text
Option 1                      Option 2
GPU 0 └── Qwen                GPU 0 + GPU 1
GPU 1 ├── Embeddings          └── Qwen avec parallélisation
      ├── Reranker
      └── Experiments
```

Les deux cartes ne doivent pas être considérées comme une seule VRAM de 32 GB sans tenir compte de la stratégie de parallélisation et du moteur d'inférence.

## 3.3 Stack logicielle indicative

```text
LLM               Qwen
Inference         vLLM ou serveur compatible  [voir §7 divergence]
Database          PostgreSQL
Vector search     pgvector / Qdrant
Lexical search    PostgreSQL FTS / OpenSearch
Embeddings        modèle embedding local
Reranker          modèle reranking local
Agent runtime     framework léger / orchestration custom
Sandbox           Docker
Numerical         NumPy, SciPy, QuantLib, C++
Research          Git
```

## 3.4 Ce qu'il ne faut PAS faire

1. Ne pas installer CUDA 13 sur cette machine.
2. Ne pas installer les NVIDIA open kernel modules sur ces V100.
3. Ne pas utiliser d'offload CPU pour les poids du modèle.
4. Ne pas commencer par 256K de contexte.
5. Ne pas exposer `llama-server` sur `0.0.0.0` sans demande explicite.
6. Ne pas monter le filesystem host complet dans le sandbox.
7. Ne pas donner à l'agent un accès root permanent.
8. Ne pas masquer une erreur par `|| true`.
9. Ne pas commencer avec 500 000 PDF — commencer par 20–50 documents extrêmement pertinents.
10. Ne pas introduire le multi-agent sans besoin concret.
11. Ne pas laisser le RAG devenir une source de vérité aveugle.
12. Ne pas exposer immédiatement des dizaines de tools MCP.

---

# 4. Structure du code / organisation des dossiers

## 4.1 Arborescence système (serveur)

```text
/opt/llm/
├── models/                 # fichiers GGUF
├── logs/                   # logs d'installation
├── scripts/healthcheck.sh
├── gpu-topology.txt
├── llama.cpp/
└── INSTALLATION-REPORT.md

/opt/agents/
└── sandbox/Dockerfile      # image sandbox de développement

/srv/sandboxes/             # sandboxes actives
/srv/repos/                 # repositories de travail
/srv/repos/agent-smoke-test/
```

Service systemd : `/etc/systemd/system/llama-server.service` (utilisateur système `llm`, `NoNewPrivileges=true`, `PrivateTmp=true`, `Restart=always`).

## 4.2 Arborescence plateforme (Harness)

```text
project/
├── api/            routes/, schemas/
├── agent/          agent.py, planner.py, policies.py
├── harness/        loop.py, context.py, state.py, evaluator.py, retry.py, limits.py
├── llm/            base.py, providers/, schemas.py
├── tools/          registry.py, executor.py, filesystem/, terminal/, git/, web/
├── memory/         manager.py, short_term.py, long_term.py, retrieval.py
├── environment/    sandbox.py, workspace.py, runtime.py
├── orchestration/  workflow.py, orchestrator.py
├── observability/  logging.py, metrics.py, tracing.py
├── persistence/    models/, repositories/
├── tests/
└── config/
```

## 4.3 Arborescence domaine quant

```text
quant-ai/
├── models/         qwen/, embeddings/, reranker/
├── agents/         orchestrator/, research/, quant/, coding/, validation/
├── knowledge/      ingestion/, parsers/, chunking/, embeddings/,
│                   retrieval/, reranking/, metadata/
├── documents/      raw/, parsed/, processed/
├── memory/         episodic/, semantic/, procedural/
├── quant/          black_scholes/, heston/, sabr/, monte_carlo/,
│                   pde/, rates/, credit/, xva/
├── sandbox/
├── tests/
├── benchmarks/
├── datasets/
├── configs/
└── infrastructure/ docker/, database/
```

## 4.4 Modèle de données conceptuel

```text
Agent                Task                  Run
├── configuration    ├── goal              ├── iterations
├── system_prompt    ├── agent             ├── LLM calls
├── tools            ├── state             ├── tool calls
├── permissions      ├── context           ├── events
└── model            ├── memory            ├── evaluation
                     └── runs              ├── tokens
                                           └── cost
```

Entités persistées : Agents, Tasks, Runs, States, Messages, Tool calls, Tool results, Memory, Events, Evaluations, Costs.

---

# 5. Détails d'implémentation clés

## 5.1 Agent Loop

```text
START → Load state → Build context → Call LLM → Interpret response
                                                      │
                        ┌── Final answer ─────────────┤
                        │                             └── Tool call
                        │                                    │
                        │                             Validate → Execute
                        │                                    │
                        │                                 Observe
                        │                                    │
                        └────────────── Update state ◄───────┘
                                            │
                                            └──► Loop
```

Limites obligatoires de la boucle :

```yaml
limits:
  max_iterations: 30
  max_tokens: 100000
  max_cost: 5.00
  timeout_seconds: 900
  max_tool_calls: 100
```

États de tâche : `PENDING`, `RUNNING`, `WAITING`, `PAUSED`, `COMPLETED`, `FAILED`, `CANCELLED` (+ `WAITING_FOR_APPROVAL`).

Exemple de State :

```json
{
  "task_id": "...",
  "status": "running",
  "goal": "...",
  "iteration": 7,
  "plan": [],
  "current_step": "...",
  "tool_calls": [],
  "files_modified": [],
  "errors": [],
  "tokens_used": 12345,
  "cost": 0.42
}
```

## 5.2 Tool Executor — pipeline obligatoire

```text
LLM Tool Call → Parse → Schema validation → Permission check
→ Guardrail check → Execute → Timeout → Result normalization
→ Logging → Return result
```

Contrat d'un tool :

```python
Tool(
    name="read_file",
    description="Read a file from the workspace",
    input_schema={...},
    permissions=[...],
)
```

Catégories : Filesystem, Terminal, Git, Web, Database, External APIs. Le LLM ne doit recevoir que les tools auxquels l'agent a réellement accès.

## 5.3 Permissions & guardrails

```yaml
permissions:
  filesystem: { read: true, write: true, delete: false }
  terminal:   { execute: true }
  network:    { enabled: false }
  git:        { commit: true, push: false }
```

Les restrictions sont appliquées au **runtime**, jamais via le prompt :

```text
LLM: "Je souhaite supprimer cette base."
Harness: → Permission DELETE_DATABASE = false → Action refusée
```

Guardrails à plusieurs niveaux : `Input → Input Guardrails → Agent → Tool Guardrails → Environment → Output Guardrails → User`.

## 5.4 Politique d'approbation humaine

| Autonome | Validation humaine requise |
|---|---|
| lecture de code, édition dans le workspace, tests, compilation, lint, `git diff`, création de commits | suppression massive, `git push`, merge, modification de secrets, accès production, base non sandboxée, installation sur le host, commande système destructive, firewall, driver, CUDA |

**Le modèle ne doit pas pouvoir modifier son propre mécanisme d'approbation.**

## 5.5 Sandbox

```text
Host
 ├── llama-server
 └── OpenHands
        └── Docker sandbox
               ├── /workspace   (repo monté)
               ├── git
               ├── compiler
               ├── tests
               └── application
```

Image sandbox dédiée dans `/opt/agents/sandbox/Dockerfile`, base Debian/Ubuntu slim, contenant au minimum :

```text
git, curl, wget, ca-certificates, build-essential, cmake, ninja-build,
pkg-config, python3, python3-pip, python3-venv, nodejs, npm,
jq, ripgrep, fd-find, unzip, zip
```

Contraintes : utilisateur non-root, `/workspace` comme cwd, pas d'accès aux secrets du host, limites CPU/RAM, timeout sur les commandes, ne jamais monter `/`, `/etc`, `/home` complet, `~/.ssh`, cloud credentials, password stores. Principe : **least privilege**.

La sandbox doit pouvoir être créée, détruite, reset, snapshotée, éventuellement clonée.

## 5.6 Mémoire — quatre types, quatre supports

```text
┌───────────────────────────────┐
│ Working Memory                │  Redis / process memory
│ contexte immédiat, tâche,     │
│ résultats récents, plan       │
└───────────────────────────────┘
┌───────────────────────────────┐
│ Episodic Memory               │  PostgreSQL + vector embeddings
│ expériences, échecs, fixes    │
└───────────────────────────────┘
┌───────────────────────────────┐
│ Long-Term / Semantic          │  PostgreSQL / Qdrant + vector + BM25
│ Heston, SABR, MC, PDE, XVA    │
└───────────────────────────────┘
┌───────────────────────────────┐
│ Procedural Memory             │  Git + fichiers + database
│ "comment faire X"             │
└───────────────────────────────┘
```

Exemple de Working Memory :

```json
{
  "task": "calibrate Heston",
  "spot": 100, "rate": 0.03, "expiry": 1.0,
  "current_model": "Heston",
  "parameters": { "kappa": 2.1, "theta": 0.04,
                  "sigma": 0.5, "rho": -0.7, "v0": 0.04 }
}
```

Exemple de mémoire procédurale (`Calibrate SABR`) : valider la surface → calculer le forward → paramètres initiaux → bornes → optimiseur → résidu → arbitrage → stocker la calibration. Support : documentation, YAML/JSON, code, workflows, tests, prompts spécialisés.

## 5.7 Quant Engine

Le moteur de pricing est **indépendant du LLM**. Le LLM appelle des APIs, il n'effectue pas le calcul.

```text
quant_engine/
    black_scholes/  binomial/  monte_carlo/  heston/  sabr/
    local_vol/      pde/       fft/          rates/   credit/  xva/
```

```python
price = heston_price(
    spot=100, strike=105, maturity=1.0, rate=0.03,
    kappa=2.0, theta=0.04, sigma=0.5, rho=-0.7, v0=0.04
)
```

Tools attendus : `black_scholes_price`, `heston_price`, `sabr_volatility`, `implied_volatility`, `build_discount_curve`, `bootstrap_curve`, `monte_carlo_price`, `calculate_greeks`, `calibrate_model`.

Chaque outil doit définir : input schema, output schema, error schema, **unités**, conventions, règles de validation.

Les unités doivent être explicites et sans ambiguïté : `rate = 0.03` (pas `3%`), `volatility = 0.20` (pas `20 volatility points`), `maturity = 1.0 years`.

## 5.8 Séparation des types d'énoncés

Une réponse doit distinguer explicitement :

| Catégorie | Exemple |
|---|---|
| **Source** | « Heston définit… » |
| **Raisonnement** | « Dans notre implémentation, nous pouvons… » |
| **Résultat calculé** | « Le prix calculé est 4.8271. » |

## 5.9 Reproductibilité

Tout résultat de pricing doit être reproductible. Stocker : model, model version, parameters, market data version, code commit, pricing method, random seed, numerical tolerance, hardware, timestamp.

```json
{
  "model": "Heston",
  "model_version": "1.2.0",
  "pricing_method": "Fourier",
  "code_commit": "abc123",
  "tolerance": 1e-8,
  "timestamp": "..."
}
```

Versionner : documents (`document_id`, `version`, `publication_date`, `ingestion_date`, `hash`, `source`), données dynamiques (`valid_from`, `valid_until`), code (commit Git), modèles (version, checkpoint, quantization).

## 5.10 Observabilité

Trois niveaux : **Logs** (INFO/WARNING/ERROR), **Metrics** (`task_duration`, `llm_latency`, `llm_tokens`, `llm_cost`, `tool_calls`, `tool_failures`, `iterations`, `success_rate`), **Traces** (reconstruction complète de la trajectoire).

Événements : `TASK_CREATED`, `TASK_STARTED`, `LLM_REQUEST`, `LLM_RESPONSE`, `TOOL_REQUEST`, `TOOL_STARTED`, `TOOL_COMPLETED`, `TOOL_FAILED`, `APPROVAL_REQUIRED`, `TASK_PAUSED`, `TASK_COMPLETED`, `TASK_FAILED`.

API : `POST/GET /agents`, `POST/GET /tasks`, `/tasks/:id/cancel|pause|resume`, `/tasks/:id/events`, `/tasks/:id/trace`, `GET /tools`, `GET /memory`.

Monitoring système : `nvidia-smi`, `nvidia-smi dmon`, `htop`, `btop`, `iotop`, `journalctl`, `docker stats`, plus `/opt/llm/scripts/healthcheck.sh` (2 GPU présents, llama-server actif, `/v1/models` répond, Docker OK, OpenHands accessible, disque et RAM suffisants).

## 5.11 Agent longue durée

```text
Task Queue → Agent Worker (LLM, filesystem, terminal, git, tests, MCP)
           → Checkpoint (état, transcript, git commit, résultats)

START → LOAD STATE → PLAN → EXECUTE TOOL → OBSERVE RESULT
      → DECIDE → CHECKPOINT → CONTINUE
```

Ne jamais dépendre uniquement de la conversation en mémoire. Persister : `task_id`, session id, current objective, current subtask, branch, last commit, test results, tool results, human feedback, status.

---

# 6. Pipeline RAG & évaluation

## 6.1 Pipeline de retrieval

```text
User Question → Query Analysis
                     │
        ┌────────────┴────────────┐
        ▼                         ▼
 Semantic Search               BM25
        └────────────┬────────────┘
                  Fusion
                     ▼
                 Reranker
                     ▼
              Top Documents
                     ▼
                   Qwen
                     ▼
                  Answer
```

Une recherche purement vectorielle est **insuffisante** en finance quantitative : les requêtes sont très lexicales (Heston, κ, θ, σ, ρ, Feller condition, CVA, PFE, SOFR, OIS, SABR). Combiner Vector Search + BM25/FTS + Metadata Filtering, puis reranker.

## 6.2 Pipeline documentaire (ingestion)

```text
Source → Download/Import → Deduplication → Parser
       → Structure reconstruction
              ├── Text
              ├── Equations
              └── Tables
       → Metadata → Chunking
              ├── Embeddings
              └── BM25
       → Knowledge DB
```

**Parsing** : ne pas faire `PDF → raw text`. Préserver équations, tableaux, figures, références, notes, titres, sous-sections, numéros d'équations.

**Équations** : données de première classe. Conserver le LaTeX, le contexte textuel, le numéro d'équation, la section, la page, le document source. Une équation isolée n'a pas toujours de sens.

$$dS_t = \mu S_t\,dt + \sqrt{v_t}\,S_t\,dW_t^S$$
$$dv_t = \kappa(\theta - v_t)\,dt + \sigma\sqrt{v_t}\,dW_t^v$$

**Chunking** : pas de découpage naïf tous les 500/1000 tokens. Chunking sémantique/structurel : Document → Chapter → Section → Subsection → Concept → Equation + explanation.

**Overlap** : léger recouvrement contrôlé (ex. 0–800 / 700–1500 / 1400–2200). Trop d'overlap augmente stockage, bruit, coûts de retrieval et duplications.

**Metadata** par chunk :

```json
{
  "document_id": "heston_1993",
  "title": "A Closed-Form Solution...",
  "author": "Steven Heston",
  "year": 1993,
  "page": 12,
  "section": "Characteristic Function",
  "topic": "stochastic_volatility",
  "asset_class": "equity",
  "document_type": "research_paper",
  "equations": true,
  "source": "..."
}
```

**Provenance** obligatoire : document, author, year, page, section, equation, source, URL, hash, license, ingestion date.

**Temporalité** — trois régimes :

| Régime | Exemples |
|---|---|
| Stable | Ito, Black-Scholes, Heston, SABR, Monte Carlo, PDE |
| Semi-stable | QuantLib, méthodes numériques, conventions de marché, implémentations |
| Très dynamique | SOFR, réglementation, ISDA, margin rules, market conventions |

```json
{ "valid_from": "2026-01-01", "valid_until": null, "source_date": "2026-01-01" }
```

**Gestion des contradictions** — le RAG peut contenir erreurs, doublons, papers contradictoires, anciennes conventions, parsing incorrect. Réponse attendue :

```text
Source A says X / Source B says Y
Difference: different assumptions / conventions
Conclusion: use X under assumption A, use Y under assumption B
```

## 6.3 Corpus — construction progressive

Qualité > quantité. Commencer par **20–50 documents extrêmement pertinents**, puis `50 → 500 → 5 000 → 50 000`. La taille du corpus doit augmenter avec la qualité du pipeline.

| Niveau | Contenu |
|---|---|
| 1 — Mathématiques | Probability, Stochastic Calculus, SDE, PDE, Numerical Analysis, Monte Carlo, Optimization, Statistics |
| 2 — Derivatives | Black-Scholes, Trees, Local Vol, Stochastic Vol, Heston, SABR, LMM, Short Rate, Credit, Jump Diffusion, Rough Vol |
| 3 — Calibration | Implied Volatility, Volatility Surface, Arbitrage-Free Surface, Parameter Calibration, Optimization |
| 4 — Numerical Methods | Monte Carlo, QMC, PDE, Finite Difference, FFT, COS, Quadrature |
| 5 — Market Practice | Yield Curves, OIS, Forward Curves, Discounting, Collateral, CSA, Multi-Curve, Conventions |
| 6 — Risk | Greeks, VaR, Expected Shortfall, Stress Testing, Scenario Analysis, P&L Attribution |
| 7 — XVA | CVA, DVA, FVA, MVA, KVA, Wrong-Way Risk, Counterparty Risk |
| 8 — Réglementation | ISDA, Basel, EMIR, Margin, Capital, Reporting |

## 6.4 Knowledge Graph (complément tardif)

Le Knowledge Graph représente explicitement les relations, le RAG récupère les passages textuels — les deux sont complémentaires.

```text
Heston
 ├── type → stochastic volatility model
 ├── uses → CIR process
 ├── parameters → κ, θ, σ, ρ, v₀
 ├── pricing → Fourier, Monte Carlo, PDE
 ├── calibration → implied volatility surface
 └── references → Heston 1993, Gatheral
```

## 6.5 Dataset d'évaluation — stratégie hybride

Position retenue : distiller un gros modèle de raisonnement est une **bonne idée mais pas la meilleure source seule**. L'optimum est **hybride** : datasets existants de très haute qualité (gold standard) **+** génération synthétique contrôlée avec vérification stricte.

### Datasets existants (base de test non contaminée, à utiliser en priorité)

| Dataset | Points forts | Usage principal |
|---|---|---|
| FinQA + ConvFinQA + TAT-QA | Raisonnement numérique multi-hop (tables + texte) | Maths / calcul |
| FinanceBench | ~10k questions sur filings réels + evidence | RAG réaliste |
| FinDER (2025) | 5 703 triplets expert-annotés, requêtes ambiguës | Évaluation RAG finance |
| FAMMA | Questions complexes (manuels + experts), multi-modales | Knowledge + reasoning |
| XFinBench, FinExam-10K, FinanceComplexQA, FinTextQA, OmniEval | Raisonnement avancé, long context, docs industriels | Couverture large |

### Génération synthétique

- **Avantages** : contrôle total des sous-domaines (maths quant, pricing, risk, code, réglementaire), CoT détaillés, variations de difficulté.
- **Risques** : hallucinations sur formules, incohérences numériques → **pipeline de vérification obligatoire** (exécution de code, LLM-as-judge, consensus multi-génération, sampling humain).

Pipeline recommandé :

```text
1. Seeds = documents réels (10-K, manuels, papers) + datasets existants
2. Génération multi-pass : question → CoT → réponse → critique
3. Filtres agressifs : code exécutable, cohérence, deduplication
   sémantique, score de difficulté
4. Test set final = majoritairement datasets existants + questions held-out
```

Modèles générateurs, par ordre de préférence :

1. **Claude Opus / top Anthropic (extended thinking)** — meilleure qualité de raisonnement structuré et précision finance ;
2. **DeepSeek-R1** — excellent rapport qualité/prix, très fort en maths et CoT ;
3. o-series / GPT-5 (reasoning élevé) ou Gemini Pro (long context).

En pratique : Claude Opus en générateur principal + DeepSeek-R1 pour le volume.

## 6.6 Benchmark interne

Créer un benchmark **avant** de considérer le système comme fiable :

```text
300 questions
  100 théorie
  100 pricing / calibration
  100 implementation / numerical methods
```

Chaque question doit avoir une réponse de référence.

## 6.7 Métriques

| Axe | Mesures |
|---|---|
| **Documentaire** | correct source ? correct equation ? correct assumptions ? correct citation ? |
| **Numérique** | price error, delta/gamma/vega error, calibration error, convergence error (ex. référence 4.8271 vs agent 4.8268 → erreur absolue 0.0003) |
| **RAG** | Recall, Precision, MRR / NDCG, Citation accuracy |
| **RAG (gain)** | Accuracy / Exact Match / Execution Accuracy avant vs après RAG, Recall@k, taux d'hallucination |
| **Agents** | tool selection, planning, code correctness, test generation, self-correction, error handling, source selection |

L'Evaluator est **séparé de l'agent** : `Agent → Result → Evaluator → PASS / FAIL / SCORE`. Il peut utiliser tests unitaires, règles, assertions, LLM judge ou validation humaine.

## 6.8 Fine-tuning — étape tardive

```text
Connaissance → RAG
Comportement → Fine-tuning / LoRA
```

Séquence : Qwen local → + tools → + RAG → + sandbox → + validation → collecte des traces → LoRA/Fine-tuning.

Les traces exploitables ont la forme : `Question → Retrieval → Reasoning → Tool calls → Code → Execution → Validation → Final Answer`.

---

# 7. Points ouverts / prochaines étapes

## 7.1 Divergences entre documents — TRANCHÉES

> Arbitrages verrouillés. La spécification d'implémentation détaillée se trouve dans
> [blueprint/](blueprint/README.md).

| Sujet | Décision | Conséquence |
|---|---|---|
| RAM système | **Non contraint** — matériel étendu si nécessaire | aucun compromis d'architecture lié à la RAM |
| Stockage | **Non contraint** — NVMe étendu si nécessaire | corpus et index peuvent croître librement |
| Moteur d'inférence | **llama.cpp** | pas de vLLM, pas d'Ollama ; GGUF, `--split-mode layer` |
| Taille du modèle | **≤ 20 GiB de poids**, layers répartis sur les 2 GPU, 100 % en VRAM | quantification Q4 ; registre de modèles en configuration pour brancher un autre modèle sans toucher au code |
| Contexte | **32768 tokens**, changeable par configuration | `configs/models.yaml` → `ctx_size` + redémarrage du service |
| Runtime agentique | **OpenHands** | **aucun Harness maison n'est développé** : pas d'agent loop, pas de tool executor, pas de state manager, pas d'orchestrateur |
| Stockage connaissance | **PostgreSQL + pgvector + Full Text Search** | pas de Qdrant, pas d'OpenSearch |

### Ce qui est effectivement développé

`corelib` (noyau) · `quantlab` (moteur quantitatif) · `kbase` (ingestion + recherche
hybride) · `agentmem` (mémoire épisodique & procédurale) · trois **serveurs MCP** ·
`evalkit` (benchmarks) · l'infrastructure. Les rôles Research / Quant / Coding /
Validation deviennent des **profils de configuration OpenHands**, pas des processus.

## 7.2 Décisions techniques restant à benchmarker

- Répartition GPU : Option 1 (Qwen sur GPU 0, embeddings/reranker sur GPU 1) vs Option 2 (parallélisation sur les 2 GPU).
- Contexte : 8K / 16K / 32K / 64K — relever pour chaque configuration VRAM GPU 0, VRAM GPU 1, RAM système, tokens/s prompt, tokens/s génération, startup time.
- Nécessité éventuelle de `-DGGML_CUDA_NO_VMM=ON` (uniquement si erreur d'allocation de mémoire virtuelle apparaît — ne pas l'activer par défaut).
- Stockage connaissance : rester sur PostgreSQL + pgvector + FTS, ou passer à PostgreSQL + Qdrant + OpenSearch.

## 7.3 Optimisations à ne traiter qu'après validation du socle

flash attention, KV cache quantifié, contexte 64K+, tuning `--tensor-split`, NCCL, paramètres de batch/prompt processing, plusieurs agents, plusieurs sandboxes, cache/retrieval de repository, gateway multi-modèles, routage local → Claude/API, agents spécialisés.

## 7.4 Montée en charge — concurrence

```text
Phase 1 : 1 LLM / 1 agent / 1 sandbox / 1 repo
Phase 2 : 1 LLM / 1 agent / 1 sandbox persistante / checkpoints
Phase 3 : 1 LLM / 2 agents / sandboxes séparées
Phase 4 : planner / coder / tester / reviewer
```

Le principal facteur limitant avec 2 × V100 sera probablement **le débit du modèle, pas la RAM système**.

## 7.5 Roadmap fonctionnelle

> Remplacée par les work packages du blueprint : [blueprint/README.md](blueprint/README.md).
> WP00 infrastructure → WP01 `corelib` → WP02 `quantlab` → WP03 MCP quant →
> WP04 ingestion → WP05 retrieval → WP06 MCP RAG → WP07 mémoire →
> WP08 OpenHands → WP09 évaluation.

**Domaine quant** — 11 phases : (1) LLM local, (2) tools BS/MC/IV/Greeks, (3) sandbox Docker Python/C++/tests, (4) RAG minimal 20–50 docs, (5) hybrid search + reranking, (6) provenance, (7) évaluation/benchmark, (8) corpus massif, (9) multi-agent, (10) episodic memory, (11) fine-tuning.

## 7.6 Livrables attendus

- `/opt/llm/INSTALLATION-REPORT.md` : OS, kernel, CPU, RAM, GPU 0/1, driver NVIDIA, CUDA toolkit, commit llama.cpp, modèle + quantification + taille + contexte testé, VRAM par GPU et RAM host pendant inférence, endpoint llama-server, versions Docker / NVIDIA Container Toolkit / OpenHands, image sandbox, checklist de tests, commandes utilisées, problèmes résolus.
- Documentation d'architecture, README, configuration d'environnement, tests, exemples d'utilisation, procédures de lancement / déploiement / debugging, description des limites connues.

## 7.7 Critères de qualité non négociables

Modularité (remplacer LLM / Tools / Memory / Database / Vector Store / Sandbox / Evaluator sans réécrire le système), sécurité (aucune action sensible ne dépend du seul comportement du LLM), observabilité, reproductibilité, résilience, contrôle (limites explicites), extensibilité.

**Les 12 principes à ne pas violer** : le LLM n'accède jamais directement au système ; tous les outils passent par le Harness ; les permissions sont contrôlées côté runtime ; les actions sont observables ; les tâches ont un état persistant ; l'agent a des limites d'exécution ; l'évaluation est distincte du raisonnement ; le système peut interrompre l'agent ; le LLM provider est abstrait ; les tools sont indépendants du LLM ; le multi-agent n'est pas introduit sans besoin concret ; la vérification objective prime sur l'auto-déclaration du LLM.

---

# 8. Checklist d'exécution — dans l'ordre

## Étape A — Préflight matériel (ne rien installer avant)

- [ ] A1. `uname -a`, `cat /etc/os-release`, `dpkg --print-architecture`
- [ ] A2. `lscpu`, `free -h`, `lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS`
- [ ] A3. `lspci -nn | grep -Ei 'NVIDIA|3D controller|VGA'`
- [ ] A4. Vérifier : amd64, Debian 13/Trixie, RAM, 2 GPU visibles, NVMe suffisant, headless
- [ ] A5. Identifier précisément les cartes : V100 PCIe ou SXM2, VRAM, bus PCIe, NVLink éventuel
- [ ] A6. Trancher les divergences du §7.1 (RAM réelle, stockage réel)

## Étape B — Préparation Debian

- [ ] B1. `sudo apt update && sudo apt full-upgrade -y && sudo reboot`
- [ ] B2. Installer les outils de base (build-essential, cmake, ninja-build, ccache, python3-venv, nvme-cli, tmux, jq, …)
- [ ] B3. Créer `/opt/llm`, `/opt/llm/models`, `/opt/llm/logs`, `/opt/agents`, `/srv/sandboxes`, `/srv/repos` + `chown`

## Étape C — Driver NVIDIA (headless)

- [ ] C1. `sudo apt install -y linux-headers-$(uname -r)`
- [ ] C2. Activer `contrib` / `non-free` si nécessaire
- [ ] C3. `apt-cache policy nvidia-driver cuda-drivers` avant de choisir une branche
- [ ] C4. Installer le driver **propriétaire** (jamais `nvidia-open`), sans pile graphique inutile
- [ ] C5. `sudo reboot`
- [ ] C6. `nvidia-smi`, `nvidia-smi -L`
- [ ] C7. `nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv` → 2 × V100, ~16384 MiB, CC 7.0

## Étape D — CUDA 12.x

- [ ] D1. Installer CUDA 12.8 ou 12.9 — **jamais CUDA 13**
- [ ] D2. `nvidia-smi`, `nvcc --version`, `which nvcc`
- [ ] D3. Installer le toolkit séparément si `nvcc` absent alors que le driver fonctionne

## Étape E — Topologie multi-GPU

- [ ] E1. `nvidia-smi topo -m | tee /opt/llm/gpu-topology.txt`
- [ ] E2. `lspci -vv | grep -A20 -Ei 'NVIDIA'`
- [ ] E3. `nvidia-smi --query-gpu=index,name,memory.total,pci.bus_id --format=csv`

## Étape F — Docker

- [ ] F1. `apt-cache policy docker-ce docker.io`
- [ ] F2. Installer Docker Engine depuis le dépôt officiel (docker-ce, cli, containerd.io, buildx, compose)
- [ ] F3. `sudo systemctl enable --now docker` + `status`
- [ ] F4. `sudo usermod -aG docker "$USER"` puis nouvelle session SSH
- [ ] F5. `docker run --rm hello-world`, `docker version`, `docker compose version`

## Étape G — NVIDIA Container Toolkit

- [ ] G1. Installer depuis le dépôt officiel NVIDIA
- [ ] G2. `sudo nvidia-ctk runtime configure --runtime=docker`
- [ ] G3. `sudo systemctl restart docker`
- [ ] G4. `docker run --rm --gpus all nvidia/cuda:12.9.1-base-ubuntu22.04 nvidia-smi` → 2 V100 visibles
- [ ] G5. **Bloquant** : ne pas continuer vers OpenHands si cet essai échoue

## Étape H — Build llama.cpp pour Volta

- [ ] H1. `git clone --depth 1 https://github.com/ggml-org/llama.cpp.git` dans `/opt/llm`
- [ ] H2. `cmake -B build -DGGML_CUDA=ON -DGGML_NATIVE=OFF -DCMAKE_CUDA_ARCHITECTURES=70 -DCMAKE_BUILD_TYPE=Release`
- [ ] H3. `cmake --build build --config Release -j"$(nproc)"`
- [ ] H4. `./build/bin/llama-server --help`, `./build/bin/llama-cli --help`
- [ ] H5. `ldd ./build/bin/llama-server | grep -Ei 'cuda|cublas'`
- [ ] H6. Si erreur VMM plus tard : rebuild avec `-DGGML_CUDA_NO_VMM=ON` (pas par défaut)

## Étape I — Modèle

- [ ] I1. Télécharger **uniquement** le fichier GGUF Q4/UD-Q4 depuis `unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF`
- [ ] I2. Placer dans `/opt/llm/models/`
- [ ] I3. `ls -lh /opt/llm/models/` + `sha256sum /opt/llm/models/*.gguf`

## Étape J — Premier test llama.cpp (sans agent)

- [ ] J1. `llama-server --list-devices`
- [ ] J2. Lancer : `-m <modèle> --host 127.0.0.1 --port 8000 --n-gpu-layers all --split-mode layer --ctx-size 32768 --flash-attn on`
- [ ] J3. `watch -n 1 nvidia-smi` → poids répartis sur les 2 GPU, pas d'usage RAM significatif pour les poids
- [ ] J4. `curl http://127.0.0.1:8000/v1/models`
- [ ] J5. `curl .../v1/chat/completions` avec un prompt de génération simple
- [ ] J6. **Bloquant** : ne pas passer à OpenHands tant que l'API ne répond pas correctement

## Étape K — Service systemd

- [ ] K1. Créer l'utilisateur système `llm` (`--system --home /opt/llm --shell /usr/sbin/nologin`)
- [ ] K2. `sudo chown -R llm:llm /opt/llm`
- [ ] K3. Créer `/etc/systemd/system/llama-server.service` avec chemins réels, `Restart=always`, `NoNewPrivileges=true`, `PrivateTmp=true`
- [ ] K4. `sudo systemctl daemon-reload && sudo systemctl enable --now llama-server && sudo systemctl status llama-server`
- [ ] K5. `journalctl -u llama-server -f`

## Étape L — OpenHands

- [ ] L1. Installer `uv` (procédure officielle) → `uv --version`
- [ ] L2. `uv tool install openhands --python 3.12` → `openhands --help`
- [ ] L3. Vérifier l'accès hôte depuis un conteneur : `docker run --rm --add-host host.docker.internal:host-gateway curlimages/curl:latest http://host.docker.internal:8000/v1/models`
- [ ] L4. `openhands serve` → GUI sur `http://localhost:3000`
- [ ] L5. Configurer : provider OpenAI-compatible, base URL `http://host.docker.internal:8000/v1`, API key `EMPTY`, model `Qwen3-Coder-30B-A3B-Instruct`

## Étape M — Sandbox

- [ ] M1. Créer `/opt/agents/sandbox/Dockerfile` (base slim + toolchain minimale listée en §5.5)
- [ ] M2. Utilisateur non-root, `/workspace` en cwd, limites CPU/RAM, timeout commandes
- [ ] M3. Vérifier qu'aucun secret du host n'est monté (`/`, `/etc`, `/home`, `~/.ssh`, credentials cloud)
- [ ] M4. Activer le Docker sandbox dans OpenHands (jamais le mode Process pour l'autonome)
- [ ] M5. `cd /srv/repos/<projet> && openhands serve --mount-cwd`

## Étape N — Git comme système de checkpoint

- [ ] N1. `git status`, `git branch` avant toute tâche autonome
- [ ] N2. Créer automatiquement une branche `agent/task-YYYYMMDD-name`
- [ ] N3. Interdire l'écriture directe sur `main` ; 1 tâche = 1 branche, 1 étape majeure = 1 commit

## Étape O — Smoke test de bout en bout

- [ ] O1. Créer `/srv/repos/agent-smoke-test` avec `README.md`, `src/`, `tests/`
- [ ] O2. Tâche : « inspecte le repo, ajoute une fonction, écris les tests, lance-les, corrige les erreurs, commit »
- [ ] O3. Valider : read → edit → run tests → observe failure → fix → run tests → `git diff` → `git commit`

## Étape P — Validation des 18 critères de réussite

- [ ] P1. Debian démarre
- [ ] P2. `nvidia-smi` montre 2 × V100
- [ ] P3. Docker démarre
- [ ] P4. Docker voit les 2 GPU
- [ ] P5. llama-server démarre automatiquement
- [ ] P6. Le modèle est entièrement chargé en VRAM
- [ ] P7. `/v1/models` répond
- [ ] P8. Une requête de génération fonctionne
- [ ] P9. OpenHands démarre
- [ ] P10. OpenHands atteint le LLM local
- [ ] P11. OpenHands crée une sandbox Docker
- [ ] P12. Le repository est monté dans `/workspace`
- [ ] P13. L'agent peut éditer du code
- [ ] P14. L'agent peut lancer les tests
- [ ] P15. L'agent peut corriger une erreur de test
- [ ] P16. L'agent peut créer un checkpoint Git
- [ ] P17. Les services redémarrent après reboot
- [ ] P18. Aucun secret du host n'est visible depuis la sandbox

## Étape Q — Monitoring, benchmark & rapport

- [ ] Q1. Créer `/opt/llm/scripts/healthcheck.sh` (GPU, llama-server, `/v1/models`, Docker, OpenHands, disque, RAM)
- [ ] Q2. Benchmarker les contextes 8K / 16K / 32K / 64K et relever VRAM GPU 0, VRAM GPU 1, RAM, tok/s prompt, tok/s génération, startup time
- [ ] Q3. Benchmarker les deux options de répartition GPU (§3.2)
- [ ] Q4. Rédiger `/opt/llm/INSTALLATION-REPORT.md` (§7.6)
- [ ] Q5. Conserver tous les logs d'installation sous `/opt/llm/logs/`

> À ce stade seulement : commencer la plateforme applicative. Ne pas ajouter de fonctionnalités agentiques avancées avant validation complète de l'étape P.

## Étape R — MVP Harness

- [ ] R1. `LLMProvider` abstrait + implémentation locale (llama-server) + `MockProvider` pour les tests
- [ ] R2. Agent (goal, context, state, tools disponibles) — sans exécution directe
- [ ] R3. Agent Loop (load state → build context → call LLM → interpret → validate → execute → observe → update state)
- [ ] R4. Context Manager (build → filter → compress → token budget check)
- [ ] R5. Tool Registry (metadata, input/output schema, permissions, availability, version)
- [ ] R6. Tool Executor (parse → schema → permission → guardrail → execute → timeout → normalize → log)
- [ ] R7. Tools MVP : `read_file`, `write_file`, `list_files`, `execute_command`
- [ ] R8. State Manager + états + persistance minimale
- [ ] R9. Permissions déclaratives (filesystem / terminal / network / git)
- [ ] R10. Limits (`max_iterations`, `max_tokens`, `max_cost`, `timeout_seconds`, `max_tool_calls`)
- [ ] R11. Logging structuré
- [ ] R12. Evaluator séparé de l'agent
- [ ] R13. Environment MVP : workspace isolé, filesystem, terminal
- [ ] R14. Tests unitaires et d'intégration + README + config + exemples + procédures (lancement, déploiement, debugging, limites connues)

## Étape S — Quant Engine (avant le RAG)

- [ ] S1. Créer `quant_engine/` avec Black-Scholes, Monte Carlo, implied volatility, Greeks
- [ ] S2. Définir pour chaque tool : input schema, output schema, error schema, **unités**, conventions, règles de validation
- [ ] S3. Exposer ces fonctions comme tools au Harness (le LLM ne calcule jamais lui-même)
- [ ] S4. Tests de non-régression numériques + valeurs de référence

## Étape T — RAG minimal

- [ ] T1. Sélectionner 20–50 documents de très haute pertinence (Niveaux 1–2 du corpus)
- [ ] T2. Pipeline d'ingestion : download → dedup → parser → reconstruction de structure (texte / équations / tables)
- [ ] T3. Préserver les équations (LaTeX, contexte, numéro, section, page, document)
- [ ] T4. Chunking sémantique/structurel avec overlap contrôlé
- [ ] T5. Metadata complètes par chunk (§6.2)
- [ ] T6. Stockage : PostgreSQL + pgvector + Full Text Search
- [ ] T7. Retriever + intégration au Context Manager (RAG optionnel, pas imposé)

## Étape U — Hybrid search & provenance

- [ ] U1. Ajouter BM25 / FTS en parallèle du vector search
- [ ] U2. Metadata filtering
- [ ] U3. Fusion + reranker local
- [ ] U4. Provenance complète (document, author, year, page, section, equation, source, URL, hash, license, ingestion date)
- [ ] U5. Champs de temporalité (`valid_from`, `valid_until`, `source_date`)
- [ ] U6. Gestion explicite des contradictions entre sources (§6.2)
- [ ] U7. Séparation Source / Raisonnement / Résultat calculé dans les réponses

## Étape V — Évaluation

- [ ] V1. Intégrer les datasets existants comme base de test non contaminée (FinQA, ConvFinQA, TAT-QA, FinanceBench, FinDER, FAMMA, …)
- [ ] V2. Construire le benchmark interne : 300 questions (100 théorie / 100 pricing-calibration / 100 implémentation-numérique) avec réponses de référence
- [ ] V3. Pipeline de génération synthétique : seeds réels → génération multi-pass → filtres agressifs
- [ ] V4. Vérification obligatoire : exécution de code, LLM-as-judge, consensus multi-génération, sampling humain
- [ ] V5. Test set final = majoritairement datasets existants + questions held-out
- [ ] V6. Mesurer : métriques documentaires, numériques, RAG (Recall, Precision, MRR/NDCG, citation accuracy), gain avant/après RAG, taux d'hallucination, métriques agents

## Étape W — V2 plateforme

- [ ] W1. Memory Manager (short-term / long-term / episodic) + mémoire procédurale
- [ ] W2. Git tools, Web tools
- [ ] W3. Human approval (`WAITING_FOR_APPROVAL`) selon la politique du §5.4
- [ ] W4. Retry Manager (exponential backoff, erreurs retryables/non-retryables, fallback)
- [ ] W5. Streaming, metrics, tracing, event system
- [ ] W6. API (`/agents`, `/tasks`, `/tasks/:id/cancel|pause|resume`, `/events`, `/trace`, `/tools`, `/memory`)
- [ ] W7. Persistence complète (Agents, Tasks, Runs, States, Messages, Tool calls/results, Memory, Events, Evaluations, Costs)
- [ ] W8. Reproductibilité des résultats de pricing (§5.9)

## Étape X — MCP (progressivement)

- [ ] X1. Filesystem contrôlé
- [ ] X2. GitHub
- [ ] X3. Git
- [ ] X4. Éventuellement PostgreSQL
- [ ] X5. Éventuellement Sentry / Jira / autres
- [ ] X6. Ne jamais exposer de serveur MCP sans authentification

## Étape Y — Corpus massif & agent longue durée

- [ ] Y1. Étendre le corpus 50 → 500 → 5 000 → 50 000, en suivant la qualité du pipeline
- [ ] Y2. Étendre aux niveaux 3–8 du corpus (calibration, numérique, market practice, risk, XVA, réglementation)
- [ ] Y3. Task Queue + Agent Worker + checkpoints persistants (§5.11)
- [ ] Y4. Episodic memory alimentée par les expériences réelles

## Étape Z — V3, multi-agent & fine-tuning

- [ ] Z1. Introduire les agents spécialisés seulement si le besoin est concret : Research, Quant, Coding, Validation
- [ ] Z2. Orchestrator + Workflow Engine + sub-agents
- [ ] Z3. Planner avec replanning dynamique + Reflection/self-correction configurable
- [ ] Z4. Model routing / fallback, exécution distribuée, scheduling
- [ ] Z5. Knowledge Graph en complément du RAG
- [ ] Z6. Collecter les traces de haute qualité (Question → Retrieval → Reasoning → Tool calls → Code → Execution → Validation → Answer)
- [ ] Z7. LoRA / SFT sur ces traces — **comportement uniquement**, jamais en remplacement du RAG
