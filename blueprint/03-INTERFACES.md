# 03 — Interfaces & contrats

> ⚠ **§2 (`quantlab`) et §5 (`evalkit`) sont obsolètes** : aucun moteur de pricing
> Python n'est développé. Les contrats de `cppdev`, `codeintel` et `qmharness` sont
> définis dans leurs WP respectifs.
> **Restent pleinement valides : §1 (`corelib`), §3 (`kbase`), §4 (`agentmem`),
> §6 (contrat MCP commun) et §7 (versionnement).** §6 est le contrat que doivent
> respecter tous les nouveaux serveurs MCP.

> Prérequis : [00-PRIMER.md](00-PRIMER.md), [01-ARCHITECTURE.md](01-ARCHITECTURE.md)
>
> **Ce fichier définit des contrats, pas des implémentations.** Tous les corps sont
> `...`. Aucun agent ne doit modifier une signature publique sans mettre à jour ce
> fichier dans le même commit.
>
> Conventions : Python 3.12, `from __future__ import annotations`, `typing.Protocol`
> pour les points d'extension, `pydantic.BaseModel` (v2) pour les DTO validés,
> `dataclasses.dataclass(frozen=True)` pour les valeurs internes pures.

---

## 1. `corelib` — noyau partagé

### 1.1 Configuration

```python
# corelib/config.py

class DatabaseSettings(BaseModel):
    host: str; port: int; database: str; user: str
    password: SecretStr
    pool_size: int
    statement_timeout_ms: int

class LLMSettings(BaseModel):
    base_url: str              # http://127.0.0.1:8000/v1
    served_model: str
    ctx_size: int              # 32768 par défaut, jamais en dur ailleurs
    request_timeout_s: int

class PathSettings(BaseModel):
    models_dir: Path; documents_dir: Path; logs_dir: Path
    repos_dir: Path; datasets_dir: Path

class Settings(BaseSettings):
    env: Literal["dev", "prod"]
    database: DatabaseSettings
    llm: LLMSettings
    paths: PathSettings
    log_level: str

def get_settings() -> Settings: ...                  # singleton, lecture .env + YAML
def load_yaml_config(name: str, model: type[T]) -> T: ...   # configs/<name>.yaml
```

**Règle** : aucun module hors `corelib.config` ne lit `os.environ` ni un fichier YAML.

### 1.2 Erreurs — voir [07-ERRORS-AND-LOGGING.md](07-ERRORS-AND-LOGGING.md)

```python
# corelib/errors.py

class AppError(Exception):
    code: ClassVar[str]
    retryable: ClassVar[bool]
    def __init__(self, message: str, *, details: Mapping[str, Any] | None = ...) -> None: ...
    def to_dto(self) -> ErrorDTO: ...

class ConfigError(AppError): ...
class ValidationError(AppError): ...
class NotFoundError(AppError): ...
class ConflictError(AppError): ...
class DependencyError(AppError): ...      # DB, modèle, service externe
class TimeoutError_(AppError): ...
class LimitExceededError(AppError): ...
class NumericalError(AppError): ...       # non-convergence, instabilité
class PermissionDeniedError(AppError): ...
```

### 1.3 Logging & observabilité

```python
# corelib/logging.py
def get_logger(name: str) -> Logger: ...
def bind_correlation_id(cid: str) -> AbstractContextManager[None]: ...

# corelib/obs.py
class ToolInvocation(BaseModel):
    id: str; ts: datetime; server: str; tool: str
    args: dict[str, Any]; args_sha: str
    status: Literal["ok", "error"]; duration_ms: int
    error_code: str | None; caller: str | None

def record_tool_invocation(inv: ToolInvocation) -> None: ...
def timed(section: str) -> AbstractContextManager[None]: ...
```

### 1.4 Base de données

```python
# corelib/db.py
def get_engine() -> Engine: ...
def session_scope() -> AbstractContextManager[Session]: ...   # commit/rollback automatiques
def check_health() -> HealthStatus: ...
def apply_migrations(target: str | None = ...) -> MigrationReport: ...
```

### 1.5 Unités — garde-fou anti-ambiguïté

```python
# corelib/units.py
Rate = NewType("Rate", float)        # décimal : 0.03 == 3 %
Vol  = NewType("Vol", float)         # décimal : 0.20 == 20 vol points
Year = NewType("Year", float)        # années fractionnaires

def as_rate(x: float) -> Rate: ...   # lève ValidationError si |x| > RATE_SANITY_MAX
def as_vol(x: float) -> Vol: ...     # lève ValidationError si x < 0 ou x > VOL_SANITY_MAX
def as_year(x: float) -> Year: ...   # lève ValidationError si x <= 0
```

> Les bornes de sanité viennent de `configs/quantlab.yaml`. Elles existent pour
> attraper l'erreur `rate=3` au lieu de `rate=0.03`.

---

## 2. `quantlab` — moteur quantitatif

### 2.1 Types de base

```python
# quantlab/types.py
class OptionType(StrEnum): CALL = "call"; PUT = "put"
class ExerciseStyle(StrEnum): EUROPEAN = "european"; AMERICAN = "american"
class DayCount(StrEnum): ACT_365F = "act/365f"; ACT_360 = "act/360"; THIRTY_360 = "30/360"
class Compounding(StrEnum): CONTINUOUS = "continuous"; ANNUAL = "annual"; SIMPLE = "simple"
```

### 2.2 Marché

```python
# quantlab/market/curves.py
class DiscountCurve(Protocol):
    def df(self, t: Year) -> float: ...
    def zero_rate(self, t: Year, compounding: Compounding) -> Rate: ...
    def forward_rate(self, t1: Year, t2: Year) -> Rate: ...

class ForwardCurve(Protocol):
    def forward(self, t: Year) -> float: ...

# quantlab/market/surfaces.py
class VolSurface(Protocol):
    def implied_vol(self, strike: float, t: Year) -> Vol: ...
    def slice(self, t: Year) -> VolSlice: ...
    def strikes(self) -> Sequence[float]: ...
    def expiries(self) -> Sequence[Year]: ...

@dataclass(frozen=True)
class MarketState:
    spot: float
    discount: DiscountCurve
    dividend: DiscountCurve | None
    valuation_date: date
    as_of: datetime
```

### 2.3 Instruments

```python
# quantlab/instruments/base.py
class Instrument(Protocol):
    kind: str
    def describe(self) -> dict[str, Any]: ...

class Payoff(Protocol):
    def __call__(self, path_or_terminal: NDArray[np.float64]) -> NDArray[np.float64]: ...

@dataclass(frozen=True)
class EuropeanOption(Instrument):
    option_type: OptionType
    strike: float
    maturity: Year
```

### 2.4 Modèles & méthodes — le cœur

```python
# quantlab/models/base.py
class ModelParams(BaseModel):
    """Base des jeux de paramètres. Chaque modèle définit sa sous-classe."""
    def validate_domain(self) -> None: ...   # lève ValidationError (ex. Feller)

class PricingModel(Protocol):
    name: str
    params_type: type[ModelParams]
    def supported_methods(self) -> frozenset[str]: ...
    def characteristic_function(self, u: complex, t: Year, params: ModelParams,
                                market: MarketState) -> complex: ...   # optionnel
    def simulate(self, params: ModelParams, market: MarketState,
                 spec: SimulationSpec) -> NDArray[np.float64]: ...     # optionnel

# quantlab/methods/base.py
class NumericalMethod(Protocol):
    name: str
    def price(self, model: PricingModel, params: ModelParams,
              instrument: Instrument, market: MarketState,
              settings: MethodSettings) -> MethodOutput: ...

class MethodSettings(BaseModel):
    seed: int | None
    tolerance: float
    max_iterations: int
    n_paths: int | None
    n_steps: int | None
    grid: GridSpec | None
    integration: IntegrationSpec | None
```

### 2.5 Point d'entrée public — la seule façon de pricer

```python
# quantlab/__init__.py  (façade)

class PricingRequest(BaseModel):
    model: str                     # "black_scholes" | "heston" | "sabr" | "local_vol"
    method: str                    # "analytic" | "fourier" | "monte_carlo" | "pde" | "binomial"
    instrument: InstrumentSpec
    market: MarketSpec
    params: dict[str, float]
    settings: MethodSettings | None

class PricingResult(BaseModel):
    price: float
    currency: str
    std_error: float | None        # Monte Carlo uniquement
    convergence: ConvergenceReport | None
    diagnostics: dict[str, Any]
    run: PricingRun                # reproductibilité, cf. §2.8

def price(request: PricingRequest) -> PricingResult: ...
def greeks(request: PricingRequest, which: Sequence[str]) -> GreeksResult: ...
def calibrate(request: CalibrationRequest) -> CalibrationResult: ...
def validate(result: PricingResult, checks: Sequence[str]) -> ValidationReport: ...
```

### 2.6 Registre & matrice de capacités

```python
# quantlab/registry.py
def get_model(name: str) -> PricingModel: ...
def get_method(name: str) -> NumericalMethod: ...
def register_model(model: PricingModel) -> None: ...
def register_method(method: NumericalMethod) -> None: ...
def supports(model: str, method: str, instrument_kind: str) -> bool: ...
def capability_matrix() -> Mapping[tuple[str, str], frozenset[str]]: ...
```

Matrice cible (phase 1 en gras, le reste plus tard) :

| modèle \ méthode | analytic | fourier | monte_carlo | pde | binomial |
|---|---|---|---|---|---|
| black_scholes | **✔** | ✔ | **✔** | ✔ | ✔ |
| heston | — | ✔ | ✔ | ✔ | — |
| sabr | ✔ (approx.) | — | ✔ | — | — |
| local_vol | — | — | ✔ | ✔ | — |

`price()` lève `ValidationError` si le couple n'est pas dans la matrice. **Jamais de fallback silencieux.**

### 2.7 Calibration, risque, validation

```python
# quantlab/calibration/base.py
class CalibrationRequest(BaseModel):
    model: str; method: str
    market: MarketSpec
    targets: list[VolQuote] | list[PriceQuote]
    initial: dict[str, float] | None
    bounds: dict[str, tuple[float, float]]
    optimizer: str                       # "differential_evolution" | "lbfgsb" | "trf"
    weights: str                         # "equal" | "vega" | "custom"
    settings: MethodSettings | None

class CalibrationResult(BaseModel):
    params: dict[str, float]
    rmse: float; max_error: float
    n_iterations: int; converged: bool
    per_target_errors: list[float]
    diagnostics: dict[str, Any]
    run: PricingRun

# quantlab/risk/greeks.py
class GreeksResult(BaseModel):
    values: dict[str, float]             # delta, gamma, vega, theta, rho…
    method: Literal["analytic", "bump"]
    bump_sizes: dict[str, float] | None

# quantlab/validation/invariants.py
def check_put_call_parity(...) -> CheckResult: ...
def check_no_arbitrage_bounds(...) -> CheckResult: ...
def check_monotonicity(...) -> CheckResult: ...
def check_feller_condition(params: ModelParams) -> CheckResult: ...
def check_surface_arbitrage_free(surface: VolSurface) -> CheckResult: ...

# quantlab/validation/convergence.py
def convergence_study(request: PricingRequest,
                      axis: Literal["n_paths", "n_steps", "grid"],
                      values: Sequence[int]) -> ConvergenceReport: ...
def cross_method_check(request: PricingRequest,
                       methods: Sequence[str], tolerance: float) -> CrossCheckReport: ...
```

### 2.8 Reproductibilité

```python
# quantlab/repro.py
class PricingRun(BaseModel):
    run_id: str
    ts: datetime
    model: str; model_version: str
    method: str
    engine_version: str
    code_commit: str | None
    seed: int | None
    tolerance: float
    inputs_sha: str
    hardware: str | None

def build_run(...) -> PricingRun: ...
```

Tout `PricingResult` / `CalibrationResult` embarque son `PricingRun`. Non optionnel.

### 2.9 Interdits `quantlab`

- Aucun import de `sqlalchemy`, `psycopg`, `httpx`, `requests`, `openai`.
- Aucune écriture de fichier hors `tests/`.
- Aucun `print`. Logging via `corelib.logging` uniquement.
- Aucun état global mutable hors registre (rempli à l'import).

---

## 3. `kbase` — connaissance & RAG

### 3.1 Schémas de domaine

```python
# kbase/schemas.py
class DocumentMeta(BaseModel):
    doc_key: str                 # slug stable, ex. "heston_1993"
    title: str
    authors: list[str]
    year: int | None
    doc_type: Literal["research_paper", "book", "documentation", "standard", "notes"]
    source_url: str | None
    license: str | None
    topic: str | None
    asset_class: str | None

class Section(BaseModel):
    section_id: str; parent_id: str | None
    level: int; ordinal: int; title: str
    page_start: int | None; page_end: int | None

class Equation(BaseModel):
    latex: str
    equation_number: str | None
    page: int | None
    symbols: list[str]

class ContentBlock(BaseModel):
    """Ordered unit produced by a `Parser`; the atom `Chunker` groups or never splits."""
    kind: Literal["text", "equation", "table", "caption"]
    text: str
    section_id: str | None
    page_start: int | None; page_end: int | None
    equation: Equation | None                # set only when kind == "equation"
    context_before: str | None; context_after: str | None   # equation-only, WP04 §5
    table_caption: str | None; table_content_md: str | None # set only when kind == "table"

class ParsedDocument(BaseModel):
    meta: DocumentMeta
    version: str
    sha256: str
    page_count: int | None
    sections: list[Section]
    blocks: list[ContentBlock]        # texte / équation / table, ordonnés
    parser_name: str; parser_version: str

class Chunk(BaseModel):
    chunk_id: str
    document_version_id: str
    section_id: str | None
    ordinal: int
    kind: Literal["text", "equation", "table", "caption"]
    content: str
    n_tokens: int
    page_start: int | None; page_end: int | None
    has_equations: bool
    valid_from: date | None; valid_until: date | None
    sha256: str

class Citation(BaseModel):
    document: str; authors: list[str]; year: int | None
    section: str | None; page: int | None
    equation_number: str | None
    source_url: str | None; sha256: str
    ingested_at: datetime

class RetrievedChunk(BaseModel):
    chunk: Chunk
    citation: Citation
    scores: dict[str, float]       # vector, lexical, fused, rerank
    rank: int
```

### 3.2 Points d'extension (Protocols)

```python
# kbase/ingestion/parsers/base.py
class Parser(Protocol):
    name: str; version: str
    def can_parse(self, path: Path) -> bool: ...
    def parse(self, path: Path, meta: DocumentMeta) -> ParsedDocument: ...

# kbase/ingestion/chunking.py
class Chunker(Protocol):
    def chunk(self, doc: ParsedDocument, policy: ChunkPolicy) -> list[Chunk]: ...

class ChunkPolicy(BaseModel):
    strategy: Literal["structural"]        # phase 1 : structurel uniquement
    target_tokens: int
    max_tokens: int
    overlap_tokens: int
    keep_equation_with_context: bool
    never_split_within: list[str]          # ex. ["equation", "table"]

# kbase/embeddings/base.py
class Embedder(Protocol):
    model_name: str; model_version: str; dim: int
    def embed_documents(self, texts: Sequence[str]) -> list[Sequence[float]]: ...
    def embed_query(self, text: str) -> Sequence[float]: ...

# kbase/retrieval/rerank.py
class Reranker(Protocol):
    model_name: str
    def rerank(self, query: str, candidates: Sequence[RetrievedChunk],
               top_k: int) -> list[RetrievedChunk]: ...
```

### 3.3 Ingestion — pipeline

```python
# kbase/ingestion/pipeline.py
class IngestionRequest(BaseModel):
    source: Literal["manifest", "path"]
    target: str
    force_reparse: bool
    dry_run: bool

class IngestionReport(BaseModel):
    run_id: str
    documents_seen: int; documents_ingested: int; documents_skipped: int
    chunks_written: int; equations_written: int
    errors: list[ErrorDTO]
    duration_ms: int

def ingest(request: IngestionRequest) -> IngestionReport: ...
```

**Call flow (obligatoire, idempotent, une transaction par document) :**

```text
ingest()
 └─ sources.resolve()          -> [SourceItem]
     └─ dedup.is_new()         -> sha256, court-circuite si inchangé
         └─ parsers.select()   -> Parser
             └─ Parser.parse() -> ParsedDocument
                 └─ structure.rebuild()
                     └─ equations.extract()
                         └─ tables.extract()
                             └─ metadata.normalize()
                                 └─ chunking.chunk()
                                     └─ embeddings.embed_documents()
                                         └─ writer.upsert()   [transaction]
```

### 3.4 Retrieval — point d'entrée unique

```python
# kbase/retrieval/query.py
class RetrievalFilters(BaseModel):
    doc_types: list[str] | None
    topics: list[str] | None
    asset_classes: list[str] | None
    year_min: int | None; year_max: int | None
    valid_at: date | None
    doc_keys: list[str] | None
    has_equations: bool | None

class RetrievalQuery(BaseModel):
    text: str
    k: int
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)  # jamais None
    strategy: Literal["hybrid", "vector", "lexical"] = "hybrid"
    rerank: bool = True

class RetrievalResult(BaseModel):
    query: RetrievalQuery
    chunks: list[RetrievedChunk]
    total_candidates: int          # taille du pool fusionné avant troncature à k
    strategy_used: Literal["hybrid", "vector", "lexical"]
    latency_ms: int
    correlation_id: str            # = kb.retrieval_logs.id (une ligne par appel)
    warnings: list[str]           # ex. "sources contradictoires détectées"

# kbase/retrieval/hybrid.py
class HybridRetriever:
    # Constructeur à paramètres explicites, pas `config: RetrievalConfig` — même
    # convention que `ingestion.pipeline.ingest()` (WP04) : `kbase/config.py` ne sert
    # qu'à la frontière CLI, jamais importé par la librairie coeur (testabilité).
    def __init__(self, *, embedder: Embedder, reranker: Reranker | None,
                 candidates_vector: int, candidates_lexical: int, rrf_k: int,
                 fts_config: str, min_score: float, rerank_top_k: int,
                 require_page: bool, require_section: bool) -> None: ...
    def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...
```

**Call flow :**

```text
HybridRetriever.retrieve()
 ├─ filters.to_sql_predicate()
 ├─ embedder.embed_query()        (sauf strategy == "lexical")
 ├─ vector.search()      ──┐
 ├─ lexical.search()     ──┤ (sauf strategy exclue)
 ├─ fusion.reciprocal_rank_fusion() / rank_single_branch()
 ├─ store.load_candidates()          (une requête, pas de N+1)
 ├─ provenance.build_citation() + assert_complete()
 ├─ rerank.rerank()          (si query.rerank ; dégradation → warning, jamais d'exception)
 ├─ contradictions.detect()
 └─ logs.record()  →  kb.retrieval_logs
```


### 3.5 Provenance

```python
# kbase/provenance.py
def build_citation(chunk: Chunk) -> Citation: ...
def assert_complete(citation: Citation) -> None: ...   # lève ValidationError si champ manquant
def format_citation(citation: Citation, style: Literal["short", "full"]) -> str: ...
```

**Invariant** : aucun `RetrievedChunk` ne quitte `kbase` sans `Citation` complète.

---

## 4. `agentmem` — mémoire

```python
# agentmem/schemas.py
class Episode(BaseModel):
    episode_id: str
    task_id: str | None
    agent_profile: str
    goal: str
    started_at: datetime; ended_at: datetime | None
    status: Literal["success", "failure", "partial", "abandoned"]
    summary: str
    actions: list[ActionRecord]
    outcome: dict[str, Any]
    lessons: list[str]
    tags: list[str]

class Procedure(BaseModel):
    name: str; version: str
    description: str
    preconditions: list[str]
    steps: list[ProcedureStep]
    postconditions: list[str]
    tags: list[str]
    source_path: str            # chemin Git, source de vérité

# agentmem/episodic.py
def remember(episode: Episode) -> str: ...
def recall(query: str, *, k: int, tags: list[str] | None,
           status: str | None) -> list[Episode]: ...
def get_episode(episode_id: str) -> Episode: ...

# agentmem/procedural.py
def list_procedures(tags: list[str] | None = ...) -> list[ProcedureSummary]: ...
def get_procedure(name: str, version: str | None = ...) -> Procedure: ...
def sync_from_git(root: Path) -> SyncReport: ...
```

**Règle** : `agentmem` ne décide jamais quoi mémoriser. C'est l'agent qui appelle
`remember` via MCP, ou un hook de fin de tâche défini dans WP08.

---

## 5. `evalkit` — évaluation

```python
# evalkit/schemas.py
class BenchmarkItem(BaseModel):
    item_id: str; suite: str
    category: Literal["theory", "pricing", "numerics", "rag", "agent"]
    question: str
    reference_answer: str | None
    reference_value: float | None
    tolerance_abs: float | None; tolerance_rel: float | None
    expected_sources: list[str]        # doc_keys attendus, pour recall
    difficulty: int
    held_out: bool

class EvalResult(BaseModel):
    run_id: str; item_id: str
    answer: str | None; value: float | None
    passed: bool; score: float
    metrics: dict[str, float]
    retrieved_doc_keys: list[str]
    latency_ms: int; tokens: int | None
    judge: str

# evalkit/runners/base.py
class Runner(Protocol):
    name: str
    def run(self, items: Sequence[BenchmarkItem], config: RunConfig) -> list[EvalResult]: ...

# evalkit/judges/*.py
class Judge(Protocol):
    name: str
    def judge(self, item: BenchmarkItem, produced: ProducedAnswer) -> JudgeVerdict: ...

# evalkit/metrics/retrieval.py
def recall_at_k(...) -> float: ...
def precision_at_k(...) -> float: ...
def mrr(...) -> float: ...
def ndcg_at_k(...) -> float: ...
def citation_accuracy(...) -> float: ...
```

Comparaison **avant/après RAG** obligatoire : `RunConfig.retrieval_enabled: bool`.

---

## 6. Couche MCP — contrat commun

Tous les serveurs MCP partagent la même forme.

```python
# <pkg>_mcp/server.py
def build_server(config: McpServerConfig) -> Server: ...
def main() -> None: ...      # choisit le transport selon config.transport

class McpServerConfig(BaseModel):
    name: str
    transport: Literal["stdio", "http"]
    host: str; port: int
    tools_allowlist: list[str]
    default_timeout_s: int
    max_result_bytes: int
```

### 6.1 Enveloppe de réponse — identique pour tous les outils

```jsonc
{
  "ok": true,
  "data": { },
  "error": null,
  "meta": {
    "server": "quantlab",
    "tool": "price_option",
    "duration_ms": 12,
    "engine_version": "0.1.0",
    "run_id": "...",          // quantlab uniquement
    "provenance": [ ]          // kbase uniquement
  }
}
```

En erreur :

```jsonc
{ "ok": false, "data": null,
  "error": { "code": "VALIDATION_ERROR", "message": "...", "details": {}, "retryable": false },
  "meta": { } }
```

### 6.2 Règles pour tout serveur MCP

| # | Règle |
|---|---|
| M1 | Le serveur MCP **ne contient aucune logique métier**. Il valide, mappe, appelle, mappe en retour, journalise. |
| M2 | Chaque outil a un **JSON Schema d'entrée et de sortie** dans `schemas.py`, source de vérité. |
| M3 | Toute exception non-`AppError` est convertie en `INTERNAL_ERROR` ; le message brut n'est jamais renvoyé au LLM. |
| M4 | Timeout par outil, obligatoire, valeur en config. |
| M5 | Résultat tronqué au-delà de `max_result_bytes`, avec `meta.truncated=true`. |
| M6 | Toute invocation est enregistrée via `corelib.obs.record_tool_invocation`. |
| M7 | La description d'outil exposée au LLM contient **les unités** et un exemple d'appel valide. |
| M8 | Un outil qui écrit doit exiger un argument `confirm: true` explicite. |

### 6.3 Catalogue d'outils exposés

**`quantlab_mcp`**

| Outil | Entrée (résumé) | Sortie |
|---|---|---|
| `quant.price_option` | model, method, instrument, market, params, settings | price, std_error, run |
| `quant.greeks` | idem + `which[]` | values, method |
| `quant.implied_vol` | price, spot, strike, maturity_years, rate, option_type | vol |
| `quant.calibrate` | model, targets, bounds, optimizer | params, rmse, converged |
| `quant.build_discount_curve` | instruments, conventions | curve_id, pillars |
| `quant.validate` | run_id \| result, checks[] | rapport par check |
| `quant.capabilities` | — | matrice modèle × méthode |

**`kbase_mcp`**

| Outil | Entrée | Sortie |
|---|---|---|
| `kb.search` | text, k, filters, strategy, rerank | chunks + citations + scores |
| `kb.get_document` | doc_key \| document_version_id | metadata + arbre de sections |
| `kb.get_equation` | doc_key, equation_number \| chunk_id | latex + contexte + citation |
| `kb.list_topics` | — | topics, asset_classes, années couvertes |
| `kb.stats` | — | nb documents/chunks, date de dernière ingestion |

**`agentmem_mcp`**

| Outil | Entrée | Sortie |
|---|---|---|
| `mem.recall` | query, k, tags, status | épisodes résumés |
| `mem.remember` | episode, `confirm=true` | episode_id |
| `mem.list_procedures` | tags | résumés |
| `mem.get_procedure` | name, version | procédure complète |

---

## 7. Contrat de version

- Chaque package publie `__version__` (SemVer).
- Un changement **incompatible** de schéma MCP incrémente le major du serveur MCP
  et est reporté dans `configs/mcp/*.yaml`.
- Les migrations SQL ne sont **jamais** modifiées après merge ; on ajoute un fichier.
- `capability_matrix()` et les JSON Schemas MCP sont **testés par snapshot** : toute
  dérive est un échec de CI (cf. [08-TESTING.md](08-TESTING.md)).
