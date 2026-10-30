# WP13 — Qualité de recherche de `kbase`

> **Contexte** : l'ingestion est solide (47 918 chunks, 20 459 équations, 606 tables,
> 100 % avec page et section). La recherche ne l'est pas. Mesures de l'audit :
> la requête « SABR implied volatility approximation » ne ramène aucun document SABR
> dans le top 3 vectoriel ; les 4 questions reformulées ou en français testées
> donnent 0 résultat lexical et du bruit vectoriel (index d'un livre, `dS = μdt + σdz`).

**Fichiers à lire** : ce fichier · [WP05](WP05-kbase-retrieval.md) · [WP04](WP04-kbase-ingestion.md) ·
`packages/kbase/src/kbase/retrieval/` · `configs/kbase.yaml`

**Dépend de** : WP16 (base de test séparée). **Parallélisable avec** : WP11, WP15.

**Règle d'exécution** : écrire l'évaluation (§1) **avant** de changer de modèle.

---

## 1. Jeu d'évaluation — #31

| Livrable |
|---|
| `benchmarks/retrieval/queries.yaml` : au moins 60 requêtes annotées avec les `doc_key` et pages attendus, mélangeant termes exacts, reformulations, français, équations. |
| `kbase eval` : recall@5, recall@10, MRR, nDCG@10, latence p50 et p95, par catégorie. Résultats datés et versionnés. |
| Baseline de l'état actuel enregistrée avant tout changement. |

**Acceptation** : commande reproductible, baseline dans le repo.

## 2. Vrai embedder configurable — #32

**Constat** : `HashingEmbedder` est instancié en dur dans `kbase/cli.py` et
`kbase_mcp/tools/search.py`. `embeddings.provider` n'est pas lu, contrairement à ce
que disent les docstrings.

| Livrable |
|---|
| Fabrique unique `build_embedder(config)`, utilisée partout, erreur explicite si le fournisseur est inconnu. |
| Serveur d'embeddings local : second `llama-server --embedding` ou service dédié. Budget VRAM à valider (deux V100 de 16 Gio, 25 Gio déjà pris par le LLM), repli CPU mesuré. |
| Modèle multilingue (français et anglais, ex. `bge-m3`), comparé sur le jeu du §1 à au moins un autre candidat. |
| Migration `vector(D)` si la dimension change, `kbase reindex`, garde au démarrage conservée, cohabitation de deux modèles pendant le reindex. |

**Acceptation** : gain mesuré par rapport à la baseline du 2026-10-31 (recall@5 : 0,75
au total, 0,50 en français), temps de reindex documenté (environ 2 h sur CPU). L'objectif
initial, « recall doublé », partait d'une mesure trop sévère au niveau des chunks.

## 3. Vrai reranker — #33

**Constat** : Jaccard pénalise les chunks longs, `rerank.model_name` vaut littéralement
`<modèle de reranking>`, et le pool vaut `k` (8), donc le reranker ne fait que réordonner.

| Livrable |
|---|
| Cross-encoder local derrière l'interface `Reranker`, activé par config. |
| Pool distinct de `k` (ex. 50 candidats pour 8 résultats). |
| Repli explicite si le modèle est absent, avec avertissement dans le résultat. |

**Acceptation** : gain de nDCG@10 mesuré, latence p95 de `kb.search` sous 2 s.

## 4. Lexical et contradictions — #34

| Constat | Livrable |
|---|---|
| `websearch_to_tsquery` exige tous les termes, donc 0 résultat en langage naturel | repli en `OR` sur les termes filtrés, ou requête `tsquery` construite ; configuration FTS séparée pour le français à évaluer sans perdre `SABR`, `SOFR`, `CVA` |
| `contradictions.detect` avertit dès que deux documents apparaissent | supprimer l'avertissement, ou le remplacer par une vraie comparaison limitée aux chunks de même sujet |

## 5. Ingestion PDF intégrée — #35

**Constat** : MinerU tourne à part (`documents/run_mineru_batch.sh`), avec des chemins
codés en dur (`/home/hadriensuper/...` dans `documents/status.sh`), et `kbase ingest`
n'accepte que du Markdown.

| Livrable |
|---|
| `Parser` PDF qui encapsule MinerU, lancé par `kbase ingest` depuis le manifeste. |
| Chemins lus depuis la config, reprise après interruption. |
| `documents/Books/` : 18 PDF pour 16 livres au manifeste, à réconcilier. |

**Acceptation** : un PDF neuf ajouté au manifeste est cherchable en une commande.
