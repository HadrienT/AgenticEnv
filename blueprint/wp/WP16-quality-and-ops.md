# WP16 — CI, base de test, sauvegardes, ménage

> **Contexte** : le lint et les tests ne tournent qu'à la main, et les tests
> d'intégration écrivent dans la base réelle.

**Fichiers à lire** : ce fichier · [08-TESTING.md](../08-TESTING.md) ·
`packages/*/tests/conftest.py` · `infra/`

**Dépend de** : — . **Bloque** : WP13 (évaluation sur une base propre). **À faire tôt.**

---

## 1. Base de test séparée — #43

**Constat vérifié** : `sample-notes`, `sample-paper`, `run-store-3` et 11 lignes
`obs` `s|t` sont dans la base réelle. Les documents de test peuvent sortir dans les
vraies recherches.

| Livrable |
|---|
| Base `agenticenv_test` dédiée, migrée par une fixture de session. Les tests refusent de tourner sur `AGX_DB_NAME=agenticenv`. |
| Purge des résidus de la base réelle : script relu, fourni en dry-run d'abord, sauvegarde préalable. |

**Acceptation** : `just test-integration` deux fois de suite, base réelle inchangée
(comptes identiques).

## 2. CI — #44

**Constat** : pas de `.github/`. Le client a déjà une CI.

| Livrable |
|---|
| GitHub Actions : ruff, mypy, import-linter, `pytest` unitaire, intégration avec un service Postgres pgvector. |
| Couverture (`pytest-cov`) publiée, seuil posé après mesure. |
| Test de dérive de protocole exécuté avec les deux repos. |
| Protection de `main` : CI obligatoire. |
| Marqueurs `numeric` et `contract` : les utiliser ou les retirer (0 test collecté). |

**Acceptation** : une PR avec une erreur de type est bloquée.

## 3. Sauvegardes — #45

**Constat** : aucune sauvegarde de Postgres. Depuis WP14, `mem.*` ne sera plus
reconstructible depuis le manifeste.

| Livrable |
|---|
| `pg_dump` quotidien via timer systemd, rétention définie, hors du volume Docker. |
| Procédure de restauration testée, décrite dans `docs/runbook.md`. |
| Rétention de `obs.tool_invocations` et `kb.retrieval_logs`. |

**Acceptation** : restauration réelle sur une base temporaire.

## 4. Ménage — #46

| À traiter |
|---|
| `infra/docker/sandbox/` : non utilisé, l'image vient de `ghcr.io/openhands`. À supprimer. |
| `infra/systemd/mcp-*.service` : remplacés ou réécrits par WP12. |
| `infra/scripts/bench-context.sh.bak` versionné. |
| Commentaires périmés : « quant-modeling n'est pas présent », docstrings « a config change ». |
| `.env.example` (`AGX_LLM_CTX_SIZE=32768`) à aligner sur `configs/models.yaml` (65536). |
| `SYNTHESE-PROJET.md` : marquer ce qui est historique. |
| `blueprint/README.md` : ordre d'exécution à jour. |
