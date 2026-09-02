# 06 — Référence de configuration

> Prérequis : [00-PRIMER.md](00-PRIMER.md)
>
> **Règle absolue** : aucune valeur de configuration en dur dans le code. Chemins,
> ports, tailles de contexte, noms de modèles, hyperparamètres, tolérances — tout
> passe par ici.

---

## 1. Hiérarchie de configuration

```text
1. Valeurs par défaut (dans les modèles pydantic de corelib.config)
2. Fichiers YAML de configs/          <- versionnés, non secrets
3. Variables d'environnement / .env   <- secrets + surcharges machine
4. Arguments CLI                      <- surcharge ponctuelle, dev uniquement
```

La priorité croît de haut en bas. `corelib.config.get_settings()` est le **seul**
point d'entrée.

---

## 2. `configs/models.yaml` — registre de modèles LLM

**C'est le fichier qui rend le modèle et le contexte interchangeables.**
Changer de modèle = changer une ligne + redémarrer le service. Aucune modification de code.

```yaml
active: qwen3-coder-30b-a3b-q4

defaults:
  host: 127.0.0.1
  port: 8000
  split_mode: layer        # jamais "tensor" sans benchmark préalable
  n_gpu_layers: all
  flash_attn: on
  cont_batching: true
  no_cpu_offload: true     # garde-fou : refuse de démarrer si offload nécessaire

models:
  qwen3-coder-30b-a3b-q4:
    path: /opt/llm/models/<fichier>.gguf
    served_name: Qwen3-Coder-30B-A3B-Instruct
    ctx_size: 32768
    approx_weights_gib: 17.5      # doit rester <= vram_budget_gib
    chat_template: null           # null = template embarqué dans le GGUF
    extra_args: []

  # Exemple de second profil, pour illustrer la modularité.
  # Ajouter un modèle = ajouter un bloc ici. Rien d'autre.
  autre-modele-q4:
    path: /opt/llm/models/<autre>.gguf
    served_name: Autre-Modele
    ctx_size: 16384
    approx_weights_gib: 12.0
    chat_template: null
    extra_args: []

limits:
  vram_budget_gib: 20            # budget de poids, décision verrouillée
  vram_total_gib: 32
  reserve_for_kv_and_buffers_gib: 10
```

### Contrat de `render-llama-env.sh`

| Entrée | Sortie |
|---|---|
| `configs/models.yaml` + `active` | `/etc/llm/llama-server.env` (variables `LLAMA_*`) |

Le script **échoue** (code non-zéro) si :
- `approx_weights_gib > limits.vram_budget_gib` ;
- le fichier GGUF est absent ou son sha256 ne correspond pas au manifeste ;
- `ctx_size` n'est pas dans la liste des valeurs benchmarkées et validées.

### Changer le contexte

```bash
# 1. éditer configs/models.yaml : ctx_size: 32768 -> 65536
# 2.
sudo infra/scripts/render-llama-env.sh
sudo systemctl restart llama-server
# 3. vérifier
infra/scripts/healthcheck.sh
```

Le service systemd lit `/etc/llm/llama-server.env` via `EnvironmentFile=` et lance
`run-llama-server.sh`, qui construit la ligne de commande. **Aucun argument de
`llama-server` n'apparaît dans l'unité systemd.**

---

## 3. `.env` — variables d'environnement

| Variable | Exemple | Secret | Utilisée par |
|---|---|---|---|
| `AGX_ENV` | `dev` | non | corelib |
| `AGX_LOG_LEVEL` | `INFO` | non | corelib |
| `AGX_DB_HOST` | `127.0.0.1` | non | corelib.db |
| `AGX_DB_PORT` | `5432` | non | corelib.db |
| `AGX_DB_NAME` | `agenticenv` | non | corelib.db |
| `AGX_DB_USER` | `app_rw` | non | corelib.db |
| `AGX_DB_PASSWORD` | — | **oui** | corelib.db |
| `AGX_LLM_BASE_URL` | `http://127.0.0.1:8000/v1` | non | evalkit, agents |
| `AGX_LLM_SERVED_MODEL` | `Qwen3-Coder-30B-A3B-Instruct` | non | evalkit |
| `AGX_LLM_CTX_SIZE` | `32768` | non | budget de contexte applicatif |
| `AGX_PATHS_MODELS_DIR` | `/opt/llm/models` | non | infra |
| `AGX_PATHS_DOCUMENTS_DIR` | `/srv/knowledge/documents` | non | kbase |
| `AGX_PATHS_REPOS_DIR` | `/srv/repos` | non | OpenHands |
| `AGX_MCP_QUANTLAB_PORT` | `8201` | non | mcp |
| `AGX_MCP_KBASE_PORT` | `8202` | non | mcp |
| `AGX_MCP_AGENTMEM_PORT` | `8203` | non | mcp |

`.env.example` contient **toutes** les variables avec des valeurs factices.
`.env` est git-ignoré. Aucun secret n'est journalisé (cf. `07-ERRORS-AND-LOGGING.md`).

---

## 4. Fichiers de configuration applicatifs

### `configs/kbase.yaml`

```yaml
embeddings:
  provider: local
  model_name: <modèle d'embedding>
  model_version: "1"
  dim: 1024                    # DOIT correspondre à la migration vector(D)
  batch_size: 32
  normalize: true

chunking:
  strategy: structural
  target_tokens: 800
  max_tokens: 1200
  overlap_tokens: 100
  keep_equation_with_context: true
  never_split_within: [equation, table]

retrieval:
  default_k: 8
  candidates_vector: 50
  candidates_lexical: 50
  fusion: rrf
  rrf_k: 60
  rerank:
    enabled: true
    model_name: <modèle de reranking>
    top_k: 8
  fts_config: simple           # pas de stemming : préserve SABR, SOFR, CVA
  min_score: 0.0

provenance:
  require_page: false          # certains formats n'ont pas de pagination
  require_section: true
```

### `configs/quantlab.yaml`

```yaml
tolerances:
  default: 1.0e-8
  monte_carlo_rel: 1.0e-3
  calibration_rmse_warn: 0.01

sanity:
  rate_abs_max: 1.0            # |rate| > 1.0 => probablement des pourcents
  vol_max: 5.0
  maturity_years_max: 100.0

monte_carlo:
  default_paths: 100000
  default_steps: 252
  antithetic: true
  default_seed: 20260101       # seed par défaut => reproductibilité

pde:
  default_space_steps: 400
  default_time_steps: 400

fourier:
  default_integration: cos
  n_terms: 256

optimizers:
  default: differential_evolution
  polish: lbfgsb
  max_iterations: 500
  multistart: 5
```

### `configs/agentmem.yaml`

```yaml
episodic:
  embed_summary: true
  recall_default_k: 5
  min_similarity: 0.3
procedural:
  source_dir: agents/procedures
  sync_on_start: true
```

### `configs/evalkit.yaml`

```yaml
suites:
  internal: [theory, pricing, numerics]
  external: []                 # activés au fur et à mesure, licences vérifiées
judges:
  numeric: {enabled: true}
  citation: {enabled: true}
  llm: {enabled: false}        # désactivé par défaut : coûteux et subjectif
thresholds:
  numeric_pass_rel: 1.0e-3
  retrieval_recall_at_8_min: 0.80
```

### `configs/mcp/<server>.yaml`

```yaml
name: quantlab
transport: http                # http | stdio  [À CONFIRMER côté OpenHands]
host: 127.0.0.1
port: 8201
default_timeout_s: 30
max_result_bytes: 262144
tools_allowlist:
  - quant.price_option
  - quant.greeks
  - quant.implied_vol
  - quant.calibrate
  - quant.build_discount_curve
  - quant.validate
  - quant.capabilities
per_tool_timeout_s:
  quant.calibrate: 300
  quant.price_option: 30
```

---

## 5. `agents/profiles/*.yaml` — profils d'agents

```yaml
role: quant
description: Choix de modèle, hypothèses, méthode numérique, calibration.
system_prompt: agents/prompts/system-common.md + agents/prompts/snippets/quant.md

mcp_tools:                      # allowlist stricte
  - quant.*
  - kb.search
  - kb.get_equation
  - mem.recall

permissions:
  filesystem: {read: true, write: false, delete: false}
  terminal:   {execute: false}
  network:    {enabled: false}
  git:        {commit: false, push: false}

limits:
  max_iterations: 30
  max_tool_calls: 100
  timeout_seconds: 900

approval_required:
  - git_push
  - merge
  - delete_many
  - host_install
```

| Profil | Outils | Écriture | Terminal | Git |
|---|---|---|---|---|
| `orchestrator` | tous (délégation) | non | non | non |
| `research` | `kb.*`, `mem.recall` | non | non | non |
| `quant` | `quant.*`, `kb.search`, `kb.get_equation` | non | non | non |
| `coding` | fs, terminal, git, `quant.*` | `/workspace` | oui | commit oui, push non |
| `validation` | `quant.validate`, terminal (pytest uniquement) | non | restreint | non |

> `[À CONFIRMER]` Le mapping exact de ces profils vers la configuration OpenHands
> (microagents, `config.toml`, allowlist MCP) est traité en [WP08](wp/WP08-openhands-integration.md).

---

## 6. Ce qui ne doit JAMAIS apparaître dans le code

| Interdit | À la place |
|---|---|
| `"/opt/llm/models/..."` | `settings.paths.models_dir` |
| `8000`, `5432`, `8201` | `settings.llm.base_url`, `settings.database.port`, config MCP |
| `32768` | `settings.llm.ctx_size` |
| `"Qwen3-Coder-30B-A3B-Instruct"` | `settings.llm.served_model` |
| `1e-8` | `configs/quantlab.yaml → tolerances.default` |
| `k=8`, `top_k=50` | `configs/kbase.yaml → retrieval.*` |
| Un mot de passe, une clé | variable d'environnement, `SecretStr` |

Test CI dédié : un scan interdit les littéraux de chemins absolus et de ports dans
`packages/**/src/**` (cf. [08-TESTING.md](08-TESTING.md) §7).
