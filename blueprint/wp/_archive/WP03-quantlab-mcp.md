# WP03 — `quantlab_mcp` (exposition MCP du moteur quant)

> **Contexte** : plateforme locale d'agents IA pour le pricing de dérivés. Le harness
> est **OpenHands** ; le LLM local (llama.cpp) appelle des outils via **MCP**.
> `quantlab` (WP02) est une bibliothèque pure qui calcule. Ce package est
> l'**adaptateur** qui l'expose au LLM.
>
> **Un serveur MCP ne contient aucune logique métier.** Il valide, mappe, appelle,
> mappe en retour, journalise. Toute tentation d'ajouter du calcul ici est une erreur
> d'architecture.

**Fichiers à lire** : ce fichier · [03-INTERFACES.md](../03-INTERFACES.md) §2 et §6 ·
[05-SEQUENCES.md](../05-SEQUENCES.md) §2 · [07-ERRORS-AND-LOGGING.md](../07-ERRORS-AND-LOGGING.md) ·
[06-CONFIG.md](../06-CONFIG.md) §4 (`configs/mcp/quantlab.yaml`)

**Dépend de** : WP02, WP01. **Bloque** : WP08.

---

## 1. Objectif

Exposer `quantlab` à OpenHands sous forme d'outils MCP au contrat strict, avec
validation d'entrée, limites, timeouts, enveloppe de réponse uniforme et
persistance des enregistrements de reproductibilité.

---

## 2. Catalogue d'outils

| Outil | Rôle | Timeout par défaut |
|---|---|---|
| `quant.capabilities` | Matrice modèle × méthode × instrument supportée | 5 s |
| `quant.price_option` | Prix d'une option | 30 s |
| `quant.greeks` | Sensibilités demandées | 60 s |
| `quant.implied_vol` | Volatilité implicite depuis un prix | 10 s |
| `quant.calibrate` | Calibration d'un modèle sur des cibles | 300 s |
| `quant.build_discount_curve` | Bootstrapping d'une courbe | 60 s |
| `quant.validate` | Exécute des checks sur un résultat ou un `run_id` | 120 s |

> `quant.capabilities` est important : il permet au LLM de **découvrir** ce qui est
> possible au lieu de deviner et d'échouer.

---

## 3. Chaîne de traitement d'un appel

```text
MCP request
 ├─ 1. allowlist (configs/mcp/quantlab.yaml) -> sinon PERMISSION_DENIED
 ├─ 2. validation JSON Schema d'entrée       -> sinon VALIDATION_ERROR
 ├─ 3. mapping.to_domain() : JSON -> PricingRequest
 │      └─ conversion + vérification d'unités (as_rate, as_vol, as_year)
 ├─ 4. timeout(par outil) autour de l'appel
 ├─ 5. quantlab.<fonction>(request)
 ├─ 6. mapping.to_dto() : résultat -> JSON
 ├─ 7. troncature si > max_result_bytes -> meta.truncated = true
 ├─ 8. persistance quant.pricing_runs (échec -> WARNING, pas d'échec de l'outil)
 ├─ 9. corelib.obs.record_tool_invocation
 └─ 10. enveloppe {ok, data, error, meta}
```

---

## 4. Conception des descriptions d'outils

La description exposée au LLM est **une partie du produit**, pas un commentaire.
Elle doit contenir, pour chaque outil :

1. ce que fait l'outil en une phrase ;
2. **les unités attendues** (`rate` décimal : 3 % ⇒ `0.03`) ;
3. les valeurs autorisées pour `model` et `method`, ou un renvoi à `quant.capabilities` ;
4. un **exemple d'appel valide complet** ;
5. ce que l'outil ne fait pas.

> Un LLM de 30B se trompe surtout sur les unités et les combinaisons non supportées.
> Une bonne description supprime la majorité des allers-retours.

---

## 5. Mapping des erreurs

| Erreur `quantlab` | Code MCP | `retryable` | Message au LLM |
|---|---|---|---|
| `ValidationError` | `VALIDATION_ERROR` | non | champ fautif + valeur attendue |
| couple non supporté | `VALIDATION_ERROR` | non | renvoie vers `quant.capabilities` |
| `NumericalError` | `NUMERICAL_ERROR` | non | diagnostic + suggestion (plus de chemins, autre méthode) |
| dépassement de timeout | `TIMEOUT` | oui | durée dépassée |
| résultat trop volumineux | `LIMIT_EXCEEDED` | non | taille + suggestion de réduire |
| outil hors allowlist | `PERMISSION_DENIED` | non | outil non disponible pour ce profil |
| exception inattendue | `INTERNAL_ERROR` | non | message générique ; trace uniquement dans les logs |

**Aucune trace Python, aucun chemin host ne remonte au LLM.**

---

## 6. Contrat de sortie

```jsonc
{
  "ok": true,
  "data": {
    "price": 0.0,
    "currency": "EUR",
    "std_error": null,
    "diagnostics": {}
  },
  "error": null,
  "meta": {
    "server": "quantlab",
    "tool": "quant.price_option",
    "duration_ms": 12,
    "engine_version": "0.1.0",
    "run_id": "01J...",
    "truncated": false
  }
}
```

`run_id` doit apparaître dans la réponse finale de l'agent à l'utilisateur : c'est ce
qui rend le chiffre auditable.

---

## 7. Transport & déploiement

- Le serveur supporte **`stdio` et `http`**, choisi par `configs/mcp/quantlab.yaml`.
  Écrire les deux dès le départ : le transport retenu côté OpenHands est
  `[À CONFIRMER]` et ne doit pas provoquer de réécriture.
- Bind `127.0.0.1:8201` en mode HTTP. Jamais `0.0.0.0`.
- `GET /health` en mode HTTP : statut + liste d'outils + version du moteur.
- Unité systemd `mcp-quantlab.service` (livrée en WP00, activée ici), `Restart=always`,
  utilisateur système dédié, `NoNewPrivileges=true`.

---

## 8. Tests

| Test | Attendu |
|---|---|
| Snapshot des JSON Schemas | toute dérive échoue la CI |
| Enveloppe de réponse | forme `{ok, data, error, meta}` pour tous les outils, succès et échec |
| Unités | `rate: 3` ⇒ `VALIDATION_ERROR` avec message actionnable |
| Couple non supporté | `VALIDATION_ERROR` renvoyant vers `capabilities` |
| Fuite d'implémentation | une exception inattendue ne révèle ni trace, ni chemin |
| Timeout | un outil lent est interrompu et renvoie `TIMEOUT` |
| Troncature | résultat volumineux ⇒ `meta.truncated=true`, réponse valide |
| Allowlist | outil retiré de la config ⇒ `PERMISSION_DENIED` |
| Persistance | `quant.pricing_runs` alimentée ; base down ⇒ outil OK + WARNING |
| Zéro métier | test de structure : aucune formule, aucun `numpy`/`scipy` importé dans ce package |

---

## 9. Critères d'acceptation

- [ ] Les 7 outils répondent, en `stdio` **et** en `http`.
- [ ] Schémas d'entrée/sortie snapshotés et commités.
- [ ] Aucun import de `numpy`/`scipy` dans `quantlab_mcp` (tout passe par `quantlab`).
- [ ] Descriptions d'outils conformes au §4 (unités + exemple + limites).
- [ ] `GET /health` OK, intégré à `healthcheck.sh`.
- [ ] `mypy --strict` passe.
- [ ] Aucune exception ne remonte non convertie.
