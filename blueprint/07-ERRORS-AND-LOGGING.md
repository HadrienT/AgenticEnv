# 07 — Erreurs, logging et observabilité

> Prérequis : [00-PRIMER.md](00-PRIMER.md)

---

## 1. Principe

> **Une erreur n'est jamais avalée.** Pas de `except: pass`, pas de `|| true`, pas
> de valeur par défaut de secours qui masque un échec.

Une erreur est soit **traitée explicitement** (avec une décision documentée), soit
**propagée** vers l'appelant sous une forme typée.

---

## 2. Taxonomie d'erreurs

Toutes les erreurs applicatives héritent de `corelib.errors.AppError`.

| Classe | `code` | `retryable` | Signification | Exemple |
|---|---|---|---|---|
| `ConfigError` | `CONFIG_ERROR` | non | Configuration invalide ou manquante | `embeddings.dim` ≠ dimension en base |
| `ValidationError` | `VALIDATION_ERROR` | non | Entrée invalide | `rate=3` au lieu de `0.03`, couple (modèle, méthode) non supporté |
| `NotFoundError` | `NOT_FOUND` | non | Ressource inexistante | `doc_key` inconnu |
| `ConflictError` | `CONFLICT` | non | État incompatible | réingestion concurrente du même sha256 |
| `PermissionDeniedError` | `PERMISSION_DENIED` | non | Action refusée par la politique | outil hors allowlist du profil |
| `DependencyError` | `DEPENDENCY_ERROR` | **oui** | Service externe en échec | PostgreSQL down, embedder indisponible |
| `TimeoutError_` | `TIMEOUT` | **oui** | Dépassement de délai | calibration > 300 s |
| `LimitExceededError` | `LIMIT_EXCEEDED` | non | Budget dépassé | résultat > `max_result_bytes`, itérations max |
| `NumericalError` | `NUMERICAL_ERROR` | non | Échec numérique | non-convergence, instabilité, matrice singulière |
| (non capturée) | `INTERNAL_ERROR` | non | Bug | tout le reste |

### Règles

| # | Règle |
|---|---|
| E1 | Chaque erreur porte `details: Mapping[str, Any]` sérialisable, **sans donnée sensible**. |
| E2 | `NumericalError` n'est **jamais** convertie en résultat. Un prix non convergé n'est pas renvoyé. |
| E3 | `retryable=true` autorise un retry côté appelant ; `false` l'interdit. |
| E4 | Toute exception non-`AppError` traversant une frontière MCP devient `INTERNAL_ERROR`, message générique. La trace complète va dans les logs, jamais au LLM. |
| E5 | Une erreur de persistance d'observabilité ne fait jamais échouer l'opération métier — elle produit un `WARNING`. |

### DTO d'erreur (frontière MCP)

```jsonc
{
  "code": "VALIDATION_ERROR",
  "message": "rate=3.0 hors bornes de sanité ; attendu un décimal (3% => 0.03)",
  "details": { "field": "market.rate", "value": 3.0, "max": 1.0 },
  "retryable": false
}
```

Le `message` est **destiné au LLM** : il doit être actionnable et indiquer la
correction attendue. Pas de trace Python, pas de chemin de fichier host.

---

## 3. Logging

### Format

JSON structuré, une ligne par événement, sur stdout (capturé par systemd/journald).

```jsonc
{
  "ts": "2026-09-02T10:31:00.123Z",
  "level": "INFO",
  "logger": "kbase.retrieval.hybrid",
  "msg": "retrieval completed",
  "correlation_id": "01J...",
  "duration_ms": 142,
  "k": 8,
  "strategy": "hybrid",
  "candidates": 100
}
```

### Niveaux

| Niveau | Usage |
|---|---|
| `DEBUG` | détail de mise au point, désactivé en prod |
| `INFO` | franchissement de frontière : entrée/sortie de composant, opération réussie |
| `WARNING` | dégradation acceptée et documentée (reranker absent, obs non persistée) |
| `ERROR` | opération échouée, `AppError` levée |
| `CRITICAL` | le service ne peut pas continuer (refus de démarrage) |

### Où logger

**Aux frontières uniquement** : entrée/sortie d'un serveur MCP, début/fin d'une
ingestion, début/fin d'un retrieval, appel DB lent. Pas de log dans les boucles de
calcul numérique.

### Corrélation

`correlation_id` est propagé de bout en bout :
tool call OpenHands → serveur MCP → bibliothèque → écriture en base. Injecté par
`corelib.logging.bind_correlation_id()`.

---

## 4. Interdits de logging

| Interdit | Raison |
|---|---|
| Mot de passe, `SecretStr`, token, clé | fuite de secret |
| Contenu intégral d'un chunk ou d'un prompt | volume + confidentialité ; loguer un hash et une longueur |
| Chemins absolus du host dans un message renvoyé au LLM | surface d'attaque |
| `print()` | non structuré, non capturé |
| Traces Python renvoyées à l'appelant MCP | fuite d'implémentation |

---

## 5. Observabilité — ce qui est persisté

| Table | Écrite par | Contenu |
|---|---|---|
| `obs.tool_invocations` | tous les serveurs MCP | serveur, outil, args (échantillonné/haché), statut, durée, code d'erreur |
| `kb.retrieval_logs` | `kbase.retrieval` | requête, filtres, stratégie, chunks retournés, scores, latence |
| `quant.pricing_runs` | `quantlab_mcp` | enregistrement complet de reproductibilité |
| `mem.episodes` | `agentmem` (sur demande de l'agent) | trajectoire de tâche, leçons |
| `eval.results` | `evalkit` | scores par item |

### Métriques dérivables (aucun système de métriques dédié en phase 1)

Ces métriques se calculent par requête SQL sur les tables ci-dessus :

```text
tool_calls_total, tool_failure_rate, tool_p50/p95_latency  <- obs.tool_invocations
retrieval_latency, retrieval_zero_results_rate             <- kb.retrieval_logs
pricing_runs_total, non_convergence_rate                   <- quant.pricing_runs
task_success_rate, avg_iterations                          <- mem.episodes
```

> Prometheus/Grafana : **hors périmètre phase 1**. Ne pas installer.

---

## 6. Health checks

Chaque service expose un état vérifiable, agrégé par `infra/scripts/healthcheck.sh`.

| Composant | Vérification | Échec = |
|---|---|---|
| GPU | `nvidia-smi` retourne 2 cartes, compute cap 7.0 | CRITICAL |
| `llama-server` | `GET /v1/models` répond 200 | CRITICAL |
| VRAM | poids chargés, aucun offload CPU détecté | CRITICAL |
| PostgreSQL | `pg_isready` + `SELECT 1` | CRITICAL |
| Migrations | version appliquée == version attendue | CRITICAL |
| Dimension embeddings | `configs/kbase.yaml.dim` == `vector(D)` en base | CRITICAL |
| MCP × 3 | `GET /health` 200 + liste d'outils non vide | ERROR |
| Docker | `docker info` + `--gpus all` fonctionnel | ERROR |
| Disque | espace libre > seuil | WARNING |
| RAM | disponible > seuil | WARNING |

Sortie : JSON sur stdout + code retour (0 = tout OK, 1 = au moins un CRITICAL).

---

## 7. Politique de retry

Le retry est **de la responsabilité de l'appelant**, jamais de la bibliothèque.

| Appelant | Politique |
|---|---|
| Serveur MCP → bibliothèque | **aucun retry**. L'erreur remonte. |
| OpenHands → serveur MCP | retry uniquement si `retryable=true`, backoff exponentiel, max 3 |
| `kbase.ingestion` → embedder | retry 3× avec backoff (dépendance locale, échec transitoire plausible) |
| `evalkit` → système sous test | aucun retry (fausserait la mesure) |

**Jamais de retry sur** : `VALIDATION_ERROR`, `NUMERICAL_ERROR`, `PERMISSION_DENIED`,
`LIMIT_EXCEEDED`, `CONFIG_ERROR`.
