# 05 — Diagrammes de séquence

> ⚠ **§2 (appel quant) et §6 (calibration Heston) sont obsolètes** : ils supposaient
> un moteur Python. Le schéma d'appel d'outil MCP qu'ils décrivent reste néanmoins
> le modèle à suivre, en remplaçant `quantlab_mcp` par `cppdev`/`codeintel`/`qmharness`.
> **§1, §3, §4, §5, §7, §8 et §9 restent valides.**

> Prérequis : [00-PRIMER.md](00-PRIMER.md), [01-ARCHITECTURE.md](01-ARCHITECTURE.md)
>
> Ces diagrammes définissent **l'ordre des appels et les responsabilités**. Ils font
> foi en cas d'ambiguïté d'implémentation.

---

## 1. Démarrage du système

```mermaid
sequenceDiagram
    autonumber
    participant SD as systemd
    participant PG as PostgreSQL
    participant LS as llama-server
    participant MCP as Serveurs MCP
    participant OH as OpenHands

    SD->>PG: start (docker compose ou unit)
    PG-->>SD: pg_isready OK
    SD->>LS: run-llama-server.sh (env rendu depuis models.yaml)
    LS->>LS: charge le GGUF, split layers sur GPU0/GPU1
    LS-->>SD: /v1/models répond
    SD->>MCP: start mcp-quantlab / mcp-kbase / mcp-agentmem
    MCP->>PG: check_health + vérif dimension embeddings
    alt dimension incohérente
        MCP-->>SD: exit non-zéro (refus de démarrer)
    end
    MCP-->>SD: /health OK
    Note over OH: lancement manuel ou user unit
    OH->>LS: GET /v1/models
    OH->>MCP: handshake MCP, liste des outils
```

**Ordre imposé** : PostgreSQL → llama-server → MCP → OpenHands. Chaque étape est
bloquante ; aucun démarrage dégradé.

---

## 2. Appel d'outil quantitatif (chemin nominal)

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant OH as OpenHands
    participant LLM as llama-server
    participant M as quantlab_mcp
    participant Q as quantlab
    participant DB as PostgreSQL

    U->>OH: "Prix d'un call Heston S=100 K=105 T=1"
    OH->>LLM: prompt + catalogue d'outils
    LLM-->>OH: tool_call quant.price_option(args)
    OH->>M: MCP request
    M->>M: valider JSON Schema
    M->>M: mapping JSON -> PricingRequest (unités vérifiées)
    M->>Q: price(request)
    Q->>Q: registry.supports(model, method, instrument)
    alt couple non supporté
        Q-->>M: ValidationError
        M-->>OH: {ok:false, error:{code:VALIDATION_ERROR}}
    else supporté
        Q->>Q: params.validate_domain() (ex. Feller)
        Q->>Q: method.price(...)
        Q->>Q: repro.build_run()
        Q-->>M: PricingResult
        M->>DB: INSERT quant.pricing_runs
        M->>DB: INSERT obs.tool_invocations
        M-->>OH: {ok:true, data:{price,...}, meta:{run_id}}
    end
    OH->>LLM: observation
    LLM-->>OH: réponse en langage naturel citant run_id
    OH-->>U: résultat
```

**Invariants** :
- Le LLM ne voit jamais une exception Python brute.
- `run_id` est toujours propagé jusqu'à la réponse finale.
- L'échec de l'écriture `obs` ne fait pas échouer l'outil (log WARNING).

---

## 3. Recherche RAG hybride

```mermaid
sequenceDiagram
    autonumber
    participant OH as OpenHands
    participant M as kbase_mcp
    participant H as HybridRetriever
    participant E as Embedder
    participant V as vector (pgvector)
    participant L as lexical (FTS)
    participant R as Reranker
    participant DB as PostgreSQL

    OH->>M: kb.search{text, k, filters, rerank:true}
    M->>H: retrieve(RetrievalQuery)
    H->>H: filters.to_sql_predicate()  (allowlist de colonnes)
    H->>E: embed_query(text)
    E-->>H: vecteur
    par recherche parallèle
        H->>V: ANN top-N + WHERE filtres
        V-->>H: candidats + distances
    and
        H->>L: FTS ts_rank top-N + WHERE filtres
        L-->>H: candidats + rangs
    end
    H->>H: fusion.reciprocal_rank_fusion()
    H->>R: rerank(query, candidats, top_k=k)
    R-->>H: candidats réordonnés
    H->>H: provenance.build_citations() + assert_complete()
    H->>H: détection de sources contradictoires -> warnings[]
    H->>DB: INSERT kb.retrieval_logs
    H-->>M: RetrievalResult
    M-->>OH: {ok:true, data:{chunks}, meta:{provenance}}
```

**Invariants** :
- Aucun chunk ne sort sans citation complète (`assert_complete` lève sinon).
- Les filtres ne sont jamais concaténés en SQL brut.
- Si le reranker est indisponible : `warnings` + résultat fusionné, jamais d'échec silencieux masqué.

---

## 4. Ingestion documentaire

```mermaid
sequenceDiagram
    autonumber
    participant CLI as kbase ingest
    participant P as pipeline
    participant S as sources
    participant D as dedup
    participant PR as Parser
    participant C as chunking
    participant E as Embedder
    participant W as writer
    participant DB as PostgreSQL

    CLI->>P: ingest(IngestionRequest)
    P->>DB: INSERT kb.ingestion_runs (status=running)
    P->>S: resolve(manifest)
    S-->>P: [SourceItem]
    loop pour chaque document
        P->>D: sha256(file)
        D->>DB: SELECT kb.document_versions WHERE sha256=?
        alt déjà ingéré et non force_reparse
            D-->>P: skip
        else nouveau
            P->>PR: parse(path, meta)
            PR-->>P: ParsedDocument (sections, blocks, équations)
            P->>P: structure.rebuild() / equations.extract() / metadata.normalize()
            P->>C: chunk(doc, ChunkPolicy)
            C-->>P: [Chunk]  (équations jamais coupées)
            P->>E: embed_documents([contenu])
            E-->>P: [vecteurs]
            P->>W: upsert(doc, chunks, embeddings)
            W->>DB: BEGIN
            W->>DB: documents / document_versions / sections / chunks
            W->>DB: chunk_embeddings / equations / tables
            W->>DB: COMMIT
        end
    end
    P->>DB: UPDATE kb.ingestion_runs (status, compteurs, errors)
    P-->>CLI: IngestionReport
```

**Invariants** :
- **Une transaction par document.** Un document échoué n'empêche pas les suivants ;
  il est consigné dans `errors[]` et le run finit en `partial`.
- L'ingestion est **idempotente** : même fichier ⇒ aucun effet.
- `dry_run` exécute tout sauf l'écriture.

---

## 5. Tâche de code avec sandbox, tests et checkpoint Git

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant OH as OpenHands
    participant LLM as llama-server
    participant SBX as Docker sandbox
    participant GIT as Git (/workspace)

    U->>OH: "Ajoute la fonction X, teste-la, commit"
    OH->>GIT: git status / git branch
    OH->>GIT: git checkout -b agent/task-YYYYMMDD-x
    loop boucle agentique (bornée par les limites)
        OH->>LLM: contexte + outils
        LLM-->>OH: tool_call (read_file / edit / run)
        OH->>SBX: exécution dans /workspace (non-root, timeout)
        SBX-->>OH: stdout, stderr, exit code
        OH->>LLM: observation
    end
    OH->>SBX: pytest
    alt tests KO
        SBX-->>OH: exit 1 + trace
        OH->>LLM: diagnostic
        Note over OH,LLM: cycle de correction
    else tests OK
        OH->>GIT: git diff
        OH->>GIT: git commit -m "..."
    end
    OH-->>U: résumé + branche + commit
```

**Invariants** :
- Jamais de commit sur `main`.
- `git push`, `merge`, suppression massive ⇒ **approbation humaine** (cf. §8).
- La sandbox n'a ni accès à PostgreSQL, ni à `llama-server`, ni aux secrets du host.

---

## 6. Scénario composite — calibration Heston de bout en bout

```mermaid
sequenceDiagram
    autonumber
    actor U as Utilisateur
    participant OH as OpenHands
    participant LLM as LLM
    participant KB as kbase_mcp
    participant QT as quantlab_mcp
    participant SBX as Sandbox
    participant MM as agentmem_mcp

    U->>OH: "Calibre Heston sur cette surface et explique les paramètres"
    OH->>MM: mem.recall("calibration Heston")
    MM-->>OH: épisodes passés (ex. "init instable -> bounds + multi-start")
    OH->>LLM: objectif + expériences passées
    LLM-->>OH: tool_call kb.search("Heston calibration Feller bounds")
    OH->>KB: kb.search
    KB-->>OH: chunks + citations
    LLM-->>OH: tool_call quant.capabilities
    QT-->>OH: (heston, fourier) supporté
    LLM-->>OH: tool_call quant.calibrate(targets, bounds, optimizer)
    OH->>QT: calibrate
    QT-->>OH: params, rmse, converged, run_id
    LLM-->>OH: tool_call quant.validate(run_id, [feller, arbitrage, cross_method])
    OH->>QT: validate
    QT-->>OH: rapport par check
    alt un check échoue
        LLM-->>OH: tool_call quant.calibrate (bounds resserrés)
    end
    LLM-->>OH: tool_call terminal (script de contrôle Monte Carlo)
    OH->>SBX: exécution
    SBX-->>OH: prix MC vs Fourier, écart
    OH->>MM: mem.remember(episode, confirm=true)
    OH-->>U: paramètres + qualité + interprétation + sources + avertissements
```

**Séparation obligatoire dans la réponse finale** :
`Source` (issue de kb.search, citée) / `Raisonnement` (produit par le LLM) /
`Résultat calculé` (issu de quantlab, avec `run_id`).

---

## 7. Exécution d'une évaluation

```mermaid
sequenceDiagram
    autonumber
    participant CLI as evalkit run
    participant S as Suite
    participant R as Runner
    participant SUT as Système sous test
    participant J as Judge
    participant DB as PostgreSQL

    CLI->>DB: INSERT eval.runs (git_commit, model, retrieval_enabled)
    CLI->>S: load(suite)
    S-->>CLI: [BenchmarkItem]
    loop pour chaque item
        CLI->>R: run(item, config)
        R->>SUT: question (kbase seul | quantlab seul | agent complet)
        SUT-->>R: réponse + sources + valeurs
        R->>J: judge(item, produced)
        J-->>R: verdict + score
        R->>DB: INSERT eval.results
    end
    CLI->>CLI: metrics.aggregate()
    CLI-->>CLI: report.markdown + report.json
```

**Règle** : la même suite est exécutée avec `retrieval_enabled=false` puis `true`.
Le gain du RAG est la différence, jamais une valeur absolue isolée.

---

## 8. Approbation humaine

```mermaid
sequenceDiagram
    autonumber
    participant LLM
    participant OH as OpenHands
    actor H as Humain

    LLM-->>OH: tool_call git_push
    OH->>OH: policy lookup (agents/profiles/*.yaml)
    OH->>H: demande d'approbation (action, cible, diff)
    alt refus
        H-->>OH: refus
        OH->>LLM: observation "action refusée par la politique"
    else accord
        H-->>OH: accord
        OH->>OH: exécution
    end
```

**Actions exigeant une approbation** : `git push`, merge, suppression massive,
modification de secrets, accès production, base non sandboxée, installation sur le
host, commande système destructive, changement firewall/driver/CUDA.

**Le modèle ne peut pas modifier cette politique** : elle vit dans des fichiers du
host hors `/workspace`.

---

## 9. Chemins d'erreur — comportement attendu

| Situation | Comportement |
|---|---|
| `llama-server` indisponible | OpenHands échoue explicitement. Aucun fallback vers une API distante. |
| PostgreSQL indisponible | Les serveurs MCP renvoient `DEPENDENCY_ERROR` `retryable=true`. `quantlab` continue de fonctionner (il ne dépend pas de la base pour calculer ; seule la persistance du `run` échoue → WARNING). |
| Reranker indisponible | Retrieval dégradé documenté : résultat fusionné + `warnings`. |
| Embedder indisponible | `kb.search` échoue en `DEPENDENCY_ERROR`. Pas de recherche lexicale seule en remplacement silencieux. |
| Timeout d'outil | `TIMEOUT` `retryable=true`, l'exécution sous-jacente est annulée. |
| Non-convergence numérique | `NUMERICAL_ERROR` `retryable=false`, avec diagnostics. **Jamais** un prix renvoyé sans convergence. |
| Dépassement de limite d'itérations | OpenHands arrête la tâche en `FAILED`, l'état est persisté. |
