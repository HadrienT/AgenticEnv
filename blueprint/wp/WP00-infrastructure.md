# WP00 — Infrastructure & runtime

> **Contexte (lecture obligatoire si vous n'avez pas lu `blueprint/00-PRIMER.md`)**
>
> Projet : plateforme locale d'agents IA pour le pricing de dérivés. Serveur Debian 13
> headless, **2 × Tesla V100 16 GiB (Volta, compute capability 7.0)**. Le harness
> agentique est **OpenHands** (on ne le réécrit pas). Le modèle est servi par
> **llama.cpp**. La connaissance vit dans **PostgreSQL + pgvector + FTS**.
>
> **Interdits absolus** : CUDA 13 · NVIDIA open kernel modules · offload CPU des poids ·
> contexte initial > 32K · bind sur `0.0.0.0` · monter `/`, `/etc`, `/home`, `~/.ssh`
> dans la sandbox · masquer une erreur avec `|| true`.
>
> RAM et stockage ne sont **pas** des contraintes (matériel extensible).

**Fichiers à lire** : ce fichier · [06-CONFIG.md](../06-CONFIG.md) §2 ·
[07-ERRORS-AND-LOGGING.md](../07-ERRORS-AND-LOGGING.md) §6 · [05-SEQUENCES.md](../05-SEQUENCES.md) §1

**Dépend de** : rien. **Bloque** : WP04 (base), WP08 (OpenHands).

---

## 1. Objectif

Rendre la machine capable de servir un modèle GGUF entièrement en VRAM sur 2 GPU,
d'exécuter du code en sandbox Docker, et d'héberger PostgreSQL — le tout démarré
automatiquement et vérifiable par un health check unique.

---

## 2. Livrables

```text
infra/
├── docker/
│   ├── compose.yaml                 # postgres (pgvector), réseau interne, bind 127.0.0.1
│   ├── postgres/Dockerfile
│   ├── postgres/initdb/00-extensions.sql
│   └── sandbox/Dockerfile + entrypoint.sh
├── systemd/
│   ├── llama-server.service
│   ├── mcp-quantlab.service         # unités créées ici, activées en WP03/06/07
│   ├── mcp-kbase.service
│   └── mcp-agentmem.service
└── scripts/
    ├── preflight.sh
    ├── render-llama-env.sh
    ├── run-llama-server.sh
    ├── healthcheck.sh
    ├── bench-context.sh
    └── gpu-report.sh
configs/
├── models.yaml
└── llama-server.env.j2
docs/runbook.md
/opt/llm/INSTALLATION-REPORT.md      # généré, hors Git
```

---

## 3. Ordre d'exécution imposé

Chaque étape est **bloquante**. Ne pas passer à la suivante si elle échoue.

| # | Étape | Vérification |
|---|---|---|
| 1 | `preflight.sh` — inventaire, **lecture seule** | amd64, Debian 13, 2 GPU en `lspci`, disque suffisant |
| 2 | Mise à jour système + outils de base + arborescence `/opt/llm`, `/opt/agents`, `/srv/sandboxes`, `/srv/repos` | — |
| 3 | Driver NVIDIA **propriétaire** (jamais `nvidia-open`) + `linux-headers-$(uname -r)` | `nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv` → 2 × V100, ~16384 MiB, **7.0** |
| 4 | CUDA **12.x** (12.8 ou 12.9) | `nvcc --version` ; `nvidia-smi` et `nvcc` peuvent différer, c'est normal |
| 5 | `gpu-report.sh` → `/opt/llm/gpu-topology.txt` | topologie et NVLink éventuel consignés |
| 6 | Docker Engine (dépôt officiel) | `docker run --rm hello-world` |
| 7 | NVIDIA Container Toolkit + `nvidia-ctk runtime configure --runtime=docker` | `docker run --rm --gpus all <image cuda 12.x> nvidia-smi` → 2 GPU |
| 8 | Build llama.cpp ciblant Volta | voir §4 |
| 9 | Téléchargement du GGUF (≤ 20 GiB de poids) | `sha256sum` consigné dans `configs/models.yaml` |
| 10 | Test manuel `llama-server` | voir §5 |
| 11 | Utilisateur système `llm` + service systemd | `systemctl status llama-server` |
| 12 | PostgreSQL + pgvector | `pg_isready`, extensions présentes |
| 13 | Image sandbox | voir §6 |
| 14 | `healthcheck.sh` | code retour 0 |

> **Point bloquant n°1** : si l'étape 7 échoue, ne pas continuer.
> **Point bloquant n°2** : si l'étape 10 échoue, ne pas passer à WP08.

---

## 4. Build llama.cpp

```bash
cmake -B build \
  -DGGML_CUDA=ON \
  -DGGML_NATIVE=OFF \
  -DCMAKE_CUDA_ARCHITECTURES=70 \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j"$(nproc)"
```

| Règle |
|---|
| `CMAKE_CUDA_ARCHITECTURES=70` est **obligatoire** (Volta). Si `nvcc` refuse `70`, le toolkit CUDA est trop récent : revenir en 12.x. **Ne jamais contourner en ciblant une architecture plus récente.** |
| Vérifier `ldd build/bin/llama-server \| grep -Ei 'cuda\|cublas'`. |
| `-DGGML_CUDA_NO_VMM=ON` **uniquement** si une erreur d'allocation de mémoire virtuelle apparaît à l'exécution. Pas par défaut. |
| Consigner le commit llama.cpp dans le rapport d'installation. |

---

## 5. Lancement du modèle — chaîne de configuration

```text
configs/models.yaml
        │  render-llama-env.sh
        ▼
/etc/llm/llama-server.env      (LLAMA_MODEL_PATH, LLAMA_CTX_SIZE, LLAMA_PORT, …)
        │  EnvironmentFile=
        ▼
llama-server.service ──ExecStart──> /opt/llm/scripts/run-llama-server.sh
                                             │ construit la ligne de commande
                                             ▼
                                        llama-server
```

**Aucun argument de `llama-server` ne doit apparaître dans l'unité systemd.**
C'est ce qui rend le modèle et le contexte interchangeables (décision verrouillée).

Paramètres de départ : `--host 127.0.0.1 --port 8000 --n-gpu-layers all
--split-mode layer --ctx-size 32768 --flash-attn on`.

`render-llama-env.sh` échoue si :
- `approx_weights_gib > limits.vram_budget_gib` (20 GiB) ;
- le GGUF est absent ou son sha256 ne correspond pas ;
- `ctx_size` n'est pas dans la liste des valeurs validées.

### Vérification VRAM (critère de réussite)

`watch -n 1 nvidia-smi` pendant le chargement :
- poids répartis sur **les deux** GPU ;
- **aucune** utilisation significative de RAM système pour les poids ;
- somme VRAM utilisée cohérente avec `approx_weights_gib` + KV cache.

Si le modèle ne tient pas : **réduire le contexte ou la quantification**. Jamais d'offload.

---

## 6. Image sandbox

```text
Base : Debian/Ubuntu slim récent
Contenu : git, curl, wget, ca-certificates, build-essential, cmake, ninja-build,
          pkg-config, python3, python3-pip, python3-venv, nodejs, npm,
          jq, ripgrep, fd-find, unzip, zip
Plus  : quantlab installé (lecture seule) — ajouté après WP02
```

| Contrainte | Détail |
|---|---|
| Utilisateur | non-root, UID/GID fixes |
| Répertoire de travail | `/workspace` |
| Montage | **uniquement** `/srv/repos/<projet>` → `/workspace` |
| Réseau | désactivé par défaut ; si activé, pas d'accès à `127.0.0.1:5432` ni `:8000` du host |
| Ressources | limites CPU et mémoire explicites |
| Timeout | sur toute commande exécutée |
| Jamais monté | `/`, `/etc`, `/home`, `~/.ssh`, credentials cloud, password stores |

---

## 7. PostgreSQL

| Élément | Valeur |
|---|---|
| Bind | `127.0.0.1:5432` uniquement |
| Extensions | `vector`, `pg_trgm`, `unaccent` (voir `initdb/00-extensions.sql`) |
| Base | `agenticenv` |
| Rôles | `migrator` (DDL), `app_rw` (services), `app_ro` (evalkit) |
| Volume | persistant, sur le NVMe |
| Mot de passe | variable d'environnement, jamais en clair dans `compose.yaml` |

Les migrations elles-mêmes sont livrées par WP01/WP04/WP07/WP09.

---

## 8. `healthcheck.sh` — contrat

Sortie : JSON sur stdout, code retour 0 (tout OK) ou 1 (au moins un CRITICAL).

```jsonc
{
  "ok": true,
  "checks": [
    {"name": "gpu_count",        "status": "ok", "detail": "2 x Tesla V100, cc 7.0"},
    {"name": "llama_server",     "status": "ok", "detail": "GET /v1/models 200"},
    {"name": "no_cpu_offload",   "status": "ok"},
    {"name": "postgres",         "status": "ok"},
    {"name": "migrations",       "status": "ok", "detail": "0006"},
    {"name": "mcp_quantlab",     "status": "ok"},
    {"name": "mcp_kbase",        "status": "ok"},
    {"name": "mcp_agentmem",     "status": "ok"},
    {"name": "docker_gpus",      "status": "ok"},
    {"name": "disk_free",        "status": "ok"},
    {"name": "ram_free",         "status": "ok"}
  ]
}
```

---

## 9. Benchmark de contexte

`bench-context.sh` mesure, pour `ctx_size ∈ {8192, 16384, 32768, 65536}` :

```text
VRAM GPU0 · VRAM GPU1 · RAM système · tok/s prompt · tok/s génération · temps de démarrage
```

Résultats consignés dans `/opt/llm/INSTALLATION-REPORT.md`. Les valeurs validées
alimentent la liste autorisée de `ctx_size` dans `render-llama-env.sh`.

Benchmarker aussi les deux répartitions GPU :
- **Option 1** : modèle sur GPU 0, embeddings/reranker sur GPU 1 ;
- **Option 2** : modèle réparti sur les 2 GPU (`split-mode layer`).

---

## 10. Critères d'acceptation

- [ ] `nvidia-smi` montre 2 × V100, compute capability 7.0.
- [ ] `nvcc --version` en 12.x.
- [ ] `docker run --gpus all` voit les 2 GPU.
- [ ] `llama-server` compilé avec CUDA, ciblant `sm_70`.
- [ ] Modèle chargé **100 % en VRAM**, réparti sur les 2 GPU, aucun offload.
- [ ] `GET /v1/models` répond ; une génération courte fonctionne.
- [ ] Changer `ctx_size` dans `configs/models.yaml` + restart suffit à changer le contexte.
- [ ] Changer `active` dans `configs/models.yaml` suffit à changer de modèle.
- [ ] PostgreSQL up, extensions présentes, bind `127.0.0.1`.
- [ ] Image sandbox : non-root, `/workspace`, aucun secret host visible.
- [ ] `healthcheck.sh` retourne 0.
- [ ] Tous les services remontent après `reboot`.
- [ ] `/opt/llm/INSTALLATION-REPORT.md` rempli, logs sous `/opt/llm/logs/`.

---

## 11. Pièges connus

| Piège | Conduite à tenir |
|---|---|
| CMake choisit une architecture CUDA non-Volta | Corriger le toolkit, jamais l'architecture cible |
| Erreur VMM au chargement | Rebuild avec `-DGGML_CUDA_NO_VMM=ON` |
| Le conteneur ne résout pas `host.docker.internal` sous Linux | `--add-host host.docker.internal:host-gateway` |
| `nvidia-smi` et `nvcc` affichent des versions différentes | Normal, ce sont des couches distinctes |
| Modèle trop gros pour le contexte demandé | Réduire contexte ou quantification. **Jamais d'offload** |
| Tentation d'installer Ollama « pour tester vite » | Interdit comme composant principal |
