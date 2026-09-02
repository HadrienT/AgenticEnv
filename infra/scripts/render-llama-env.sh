#!/usr/bin/env bash
# Translates the active profile of configs/models.yaml into /etc/llm/llama-server.env.
# Fails (non-zero) if: approx_weights_gib > limits.vram_budget_gib; the GGUF is
# missing or its sha256 does not match the manifest; ctx_size is not in
# validated_ctx_sizes. No llama-server argument is hardcoded anywhere else.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MODELS_YAML="${REPO_ROOT}/configs/models.yaml"
TEMPLATE="${REPO_ROOT}/configs/llama-server.env.j2"
OUT_FILE="${AGX_LLAMA_ENV_FILE:-/etc/llm/llama-server.env}"

[[ -f "$MODELS_YAML" ]] || { echo "ERROR: $MODELS_YAML not found" >&2; exit 1; }
[[ -f "$TEMPLATE" ]] || { echo "ERROR: $TEMPLATE not found" >&2; exit 1; }

# Minimal indentation-based YAML reader, scoped to the models.yaml grammar
# (scalars, nested maps, flat lists). No PyYAML dependency at this bootstrap stage.
rendered="$(MODELS_YAML="$MODELS_YAML" TEMPLATE="$TEMPLATE" python3 <<'PY'
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
cfg = parse_yaml_lite(models_yaml)

active = cfg.get("active")
models = cfg.get("models", {})
defaults = cfg.get("defaults", {})
limits = cfg.get("limits", {})
validated_ctx_sizes = cfg.get("validated_ctx_sizes", [])

if active not in models:
    print(f"ERROR: active model '{active}' not found in models.yaml", file=sys.stderr)
    sys.exit(1)
model = models[active]

ctx_size = model.get("ctx_size")
if ctx_size not in validated_ctx_sizes:
    print(f"ERROR: ctx_size {ctx_size} is not in validated_ctx_sizes {validated_ctx_sizes}. "
          f"Run infra/scripts/bench-context.sh first.", file=sys.stderr)
    sys.exit(1)

approx_weights = model.get("approx_weights_gib")
vram_budget = limits.get("vram_budget_gib")
if approx_weights is None or vram_budget is None or approx_weights > vram_budget:
    print(f"ERROR: approx_weights_gib={approx_weights} exceeds limits.vram_budget_gib={vram_budget}",
          file=sys.stderr)
    sys.exit(1)

model_path = model.get("path")
if not model_path or not os.path.isfile(model_path):
    print(f"ERROR: GGUF not found at {model_path}. Download it and update configs/models.yaml "
          f"(see WP00 §3 step 9).", file=sys.stderr)
    sys.exit(1)

expected_sha = model.get("sha256")
if not expected_sha:
    print(f"ERROR: models.yaml has no sha256 for '{active}'. Compute it with "
          f"'sha256sum {model_path}' and record it in configs/models.yaml.", file=sys.stderr)
    sys.exit(1)

h = hashlib.sha256()
with open(model_path, "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 20), b""):
        h.update(chunk)
actual_sha = h.hexdigest()
if actual_sha != expected_sha:
    print(f"ERROR: sha256 mismatch for {model_path}: expected {expected_sha}, got {actual_sha}",
          file=sys.stderr)
    sys.exit(1)

def render(key, value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, list):
        return " ".join(str(v) for v in value)
    return str(value)

context = {
    "LLAMA_MODEL_PATH": model_path,
    "LLAMA_SERVED_NAME": model.get("served_name", active),
    "LLAMA_HOST": defaults.get("host", "127.0.0.1"),
    "LLAMA_PORT": defaults.get("port", 8000),
    "LLAMA_CTX_SIZE": ctx_size,
    "LLAMA_N_GPU_LAYERS": defaults.get("n_gpu_layers", "all"),
    "LLAMA_SPLIT_MODE": defaults.get("split_mode", "layer"),
    "LLAMA_FLASH_ATTN": render("flash_attn", defaults.get("flash_attn", True)),
    "LLAMA_CONT_BATCHING": render("cont_batching", defaults.get("cont_batching", True)),
    "LLAMA_CHAT_TEMPLATE": model.get("chat_template") or "",
    "LLAMA_EXTRA_ARGS": render("extra_args", model.get("extra_args", [])),
    "LLAMA_BIN": os.environ.get("AGX_LLAMA_BIN", "/opt/llm/llama.cpp/build/bin/llama-server"),
}

with open(template_path, encoding="utf-8") as fh:
    tpl = fh.read()

for key, value in context.items():
    tpl = tpl.replace("{{ " + key + " }}", render(key, value))

sys.stdout.write(tpl)
PY
)"

out_dir="$(dirname "$OUT_FILE")"
if [[ -d "$out_dir" && -w "$out_dir" ]]; then
  printf '%s\n' "$rendered" > "$OUT_FILE"
  echo "written: $OUT_FILE"
else
  fallback="/tmp/llama-server.env.generated"
  printf '%s\n' "$rendered" > "$fallback"
  echo "WARNING: cannot write to $OUT_FILE (missing dir or permissions)." >&2
  echo "Generated at $fallback instead. Install it with:" >&2
  echo "  sudo mkdir -p $out_dir && sudo install -m 0644 $fallback $OUT_FILE" >&2
fi
