# WP08g — Écriture automatique dans le repo à chaque fin de tour

> **Décision de l'opérateur (2026-10-31)** : la relecture fichier par fichier n'est
> pas utilisée. Les éditions de l'agent rejoignent le vrai repo sans validation, à
> la fin de chaque tour, comme avec Claude Code. **Ce WP abroge l'invariant de
> WP08d** « seul un `apply_changes` explicite écrit dans le repo ». La copie sandbox
> reste : l'agent peut toujours tout casser sans toucher le repo pendant un tour.

**Fichiers à lire** : ce fichier · [WP08d](WP08d-sandbox-working-copy.md) ·
`agenticenv-chat/blueprint/wp/C15-sandbox-working-copy.md`

**Dépend de** : WP08d. **Issue** : #20. **Côté client** : HadrienT/agenticenv-chat#12.

**État (2026-10-31)** : code et tests faits sur les branches `feat/auto-apply` des
deux repos, non commités. Reste le test manuel de bout en bout.

---

## 1. Le modèle

`refs/agenticenv/applied` marque ce que le repo hôte a déjà reçu. Une seule
opération, `_sync_to_host`, couvre tous les cas :

| Déclencheur | Effet |
|---|---|
| Fin de tour, y compris annulé ou en erreur | les fichiers qui diffèrent d'`applied` sont écrits sur l'hôte |
| `restore_checkpoint` (Undo turn) | la copie est restaurée, puis le même sync propage l'annulation |
| `apply_changes` avec `force` | sert uniquement à écraser un conflit signalé |

| Règle |
|---|
| Une session `read_only` (Ask / Plan) n'écrit jamais. |
| Un fichier modifié sur l'hôte pendant la session n'est jamais écrasé sans demande : il part dans `skipped`, le reste du tour est écrit. |
| `applied` n'avance que s'il ne reste aucun conflit : un fichier sauté reste en attente. |
| Le snapshot des hashes hôte est pris **avant** `session_started`. |
| Un dossier non git reçoit un `git init` dans la copie uniquement. |

## 2. Corrections d'`apply.py` livrées avec ce WP

Sans elles, l'auto-apply déclencherait ces bugs à chaque tour.

| Bug | Correction |
|---|---|
| Binaire corrompu par la normalisation CRLF | contenu binaire écrit tel quel (heuristique NUL de git) |
| Renommage laissant l'ancien fichier | `git diff --no-renames` : une suppression plus un ajout |
| Bit exécutable perdu sur un nouveau fichier | `WorkingCopy.is_executable` |
| `OSError` fermant la connexion, donc le sandbox | fichier placé dans `skipped` avec la raison |
| Dossiers vides laissés après un Undo | parents vides supprimés |

## 3. Protocole

- Supprimé : `discard_changes`.
- Inchangés : `apply_changes`, `changes_applied`, `restore_checkpoint`. Le bridge
  émet désormais `changes_applied` de lui-même, avant `turn_finished`, et seulement
  si quelque chose a été écrit ou sauté.

## 4. Critères d'acceptation

- [x] `test_auto_apply.py` : écriture en fin de tour, Undo jusqu'au repo, conflit
      sauté puis écrasé, session `read_only` sans écriture, tour sans édition muet.
- [x] Tests `apply.py` et `WorkingCopy` pour chaque bug du §2.
- [x] Client : plus aucun bouton `apply` / `discard` / `revert` / `revert hunk`.
- [ ] Vérif manuelle sur un vrai sandbox : un tour avec édition, ajout, renommage,
      puis Undo, sur un repo git et sur un dossier non git.
