#!/usr/bin/env bash
# Translates the profiles of configs/models.yaml into one env file per profile,
# /etc/llm/profiles/<profile>.env (issue #16). `just llm-use <profile>` then
# points /etc/llm/llama-server.env at one of them and restarts llama-server.
#
# Usage: render-llama-env.sh [PROFILE ...]    (default: every profile)
#
# Fails (non-zero) if, for any requested profile: approx_weights_gib >
# limits.vram_budget_gib; the GGUF is missing or its sha256 does not match the
# manifest; ctx_size is not in the model's (or the global) validated_ctx_sizes.
# No llama-server argument is hardcoded anywhere else.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MODELS_YAML="${REPO_ROOT}/configs/models.yaml"
TEMPLATE="${REPO_ROOT}/configs/llama-server.env.j2"
PROFILES_DIR="${AGX_LLAMA_PROFILES_DIR:-/etc/llm/profiles}"

[[ -f "$MODELS_YAML" ]] || { echo "ERROR: $MODELS_YAML not found" >&2; exit 1; }
[[ -f "$TEMPLATE" ]] || { echo "ERROR: $TEMPLATE not found" >&2; exit 1; }

STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT

# Minimal indentation-based YAML reader, scoped to the models.yaml grammar
# (scalars, nested maps, flat lists). No PyYAML dependency at this bootstrap stage.
MODELS_YAML="$MODELS_YAML" TEMPLATE="$TEMPLATE" STAGE_DIR="$STAGE_DIR" python3 - "$@" <<'PY'
import os
import re
import sys
import hashlib

def parse_yaml_lite(path):
    with open(path, encoding="utf-8") as fh:
        raw_lines = fh.readlines()

    lines = []
    for line in raw_lines:
        stripped = line.split(" #", 1)[0].rstrip("\n")
        if not stripped.strip() or stripped.strip().startswith("#"):
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        lines.append((indent, stripped.strip()))

    def parse_scalar(tok):
        tok = tok.strip()
        if tok in ("null", "~", ""):
            return None
        if tok == "true":
            return True
        if tok == "false":
            return False
        if tok == "[]":
            return []
        if re.fullmatch(r"-?\d+", tok):
            return int(tok)
        if re.fullmatch(r"-?\d+\.\d+", tok):
            return float(tok)
        if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "\"'":
            return tok[1:-1]
        return tok

    pos = 0
    def parse_block(indent):
        nonlocal pos
        is_list = pos < len(lines) and lines[pos][1].startswith("- ") or lines[pos][1] == "-"
        if is_list:
            items = []
            while pos < len(lines) and lines[pos][0] == indent and (lines[pos][1].startswith("- ") or lines[pos][1] == "-"):
                _, content = lines[pos]
                item = content[1:].strip() if content != "-" else ""
                pos += 1
                items.append(parse_scalar(item))
            return items

        result = {}
        while pos < len(lines) and lines[pos][0] == indent:
            cur_indent, content = lines[pos]
            if ":" not in content:
                pos += 1
                continue
            key, _, value = content.partition(":")
            key = key.strip()
            value = value.strip()
            pos += 1
            if value == "":
                if pos < len(lines) and lines[pos][0] > cur_indent:
                    result[key] = parse_block(lines[pos][0])
                else:
                    result[key] = None
            else:
                result[key] = parse_scalar(value)
        return result

    return parse_block(0) if lines else {}

models_yaml = os.environ["MODELS_YAML"]
template_path = os.environ["TEMPLATE"]
stage_dir = os.environ["STAGE_DIR"]
cfg = parse_yaml_lite(models_yaml)

models = cfg.get("models") or {}
profiles = cfg.get("profiles") or {}
defaults = cfg.get("defaults") or {}
limits = cfg.get("limits") or {}
global_ctx_sizes = cfg.get("validated_ctx_sizes") or []

if not profiles:
    print("ERROR: models.yaml has no `profiles` section", file=sys.stderr)
    sys.exit(1)

requested = sys.argv[1:] or list(profiles)
for name in requested:
    if name not in profiles:
        print(f"ERROR: unknown profile '{name}' (known: {', '.join(profiles)})", file=sys.stderr)
        sys.exit(1)
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        print(f"ERROR: profile name '{name}' must match [a-z][a-z0-9-]*", file=sys.stderr)
        sys.exit(1)

def render(key, value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)

def fail(profile, msg):
    print(f"ERROR [{profile}]: {msg}", file=sys.stderr)
    sys.exit(1)

with open(template_path, encoding="utf-8") as fh:
    template = fh.read()

for profile in requested:
    key = profiles[profile]
    if key not in models:
        fail(profile, f"model '{key}' not found in models.yaml")
    model = models[key]

    ctx_size = model.get("ctx_size")
    validated = model.get("validated_ctx_sizes") or global_ctx_sizes
    if ctx_size not in validated:
        fail(profile, f"ctx_size {ctx_size} is not in validated_ctx_sizes {validated}. "
                      f"Run infra/scripts/bench-context.sh first.")

    approx_weights = model.get("approx_weights_gib")
    vram_budget = limits.get("vram_budget_gib")
    if approx_weights is None or vram_budget is None or approx_weights > vram_budget:
        fail(profile, f"approx_weights_gib={approx_weights} exceeds limits.vram_budget_gib={vram_budget}")

    llama_bin = model.get("llama_bin")
    if llama_bin and not os.access(llama_bin, os.X_OK):
        fail(profile, f"llama_bin {llama_bin} is not an executable file")

    model_path = model.get("path")
    if not model_path or not os.path.isfile(model_path):
        fail(profile, f"GGUF not found at {model_path}. Download it and update configs/models.yaml "
                      f"(see WP00 §3 step 9).")

    expected_sha = model.get("sha256")
    if not expected_sha:
        fail(profile, f"models.yaml has no sha256 for '{key}'. Compute it with "
                      f"'sha256sum {model_path}' and record it in configs/models.yaml.")

    print(f"[{profile}] checking sha256 of {model_path} ...", file=sys.stderr)
    h = hashlib.sha256()
    with open(model_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    actual_sha = h.hexdigest()
    if actual_sha != expected_sha:
        fail(profile, f"sha256 mismatch for {model_path}: expected {expected_sha}, got {actual_sha}")

    context = {
        "LLAMA_PROFILE": profile,
        "LLAMA_MODEL_PATH": model_path,
        "LLAMA_SERVED_NAME": model.get("served_name", key),
        "LLAMA_HOST": defaults.get("host", "127.0.0.1"),
        "LLAMA_PORT": defaults.get("port", 8000),
        "LLAMA_CTX_SIZE": ctx_size,
        "LLAMA_N_GPU_LAYERS": defaults.get("n_gpu_layers", "all"),
        "LLAMA_SPLIT_MODE": defaults.get("split_mode", "layer"),
        "LLAMA_FLASH_ATTN": render("flash_attn", defaults.get("flash_attn", True)),
        "LLAMA_CONT_BATCHING": render("cont_batching", defaults.get("cont_batching", True)),
        "LLAMA_NO_CPU_OFFLOAD": render("no_cpu_offload", defaults.get("no_cpu_offload", True)),
        "LLAMA_CHAT_TEMPLATE": model.get("chat_template") or "",
        "LLAMA_EXTRA_ARGS": render("extra_args", model.get("extra_args", [])),
        # A model may pin its own llama.cpp build (e.g. an architecture broken by a
        # later llama.cpp); otherwise the shared binary.
        "LLAMA_BIN": model.get("llama_bin")
        or os.environ.get("AGX_LLAMA_BIN", "/opt/llm/llama.cpp/build/bin/llama-server"),
    }
    tpl = template
    for k, value in context.items():
        tpl = tpl.replace("{{ " + k + " }}", render(k, value))
    with open(os.path.join(stage_dir, f"{profile}.env"), "w", encoding="utf-8") as out:
        out.write(tpl)
PY

if [[ -d "$PROFILES_DIR" && -w "$PROFILES_DIR" ]]; then
  for f in "$STAGE_DIR"/*.env; do
    install -m 0644 "$f" "$PROFILES_DIR/"
    echo "written: $PROFILES_DIR/$(basename "$f")"
  done
else
  fallback="/tmp/llama-profiles"
  mkdir -p "$fallback"
  cp "$STAGE_DIR"/*.env "$fallback/"
  echo "WARNING: cannot write to $PROFILES_DIR (missing dir or permissions)." >&2
  echo "Generated in $fallback instead. Install with:" >&2
  echo "  sudo install -d -m 0755 $PROFILES_DIR && sudo install -m 0644 $fallback/*.env $PROFILES_DIR/" >&2
fi
