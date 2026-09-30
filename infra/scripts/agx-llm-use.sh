#!/usr/bin/env bash
# Privileged half of `just llm-use <profile>` (issue #16): points
# /etc/llm/llama-server.env at /etc/llm/profiles/<profile>.env and restarts
# llama-server. Only one model is loaded at a time.
#
# Installed root-owned to /usr/local/sbin/agx-llm-use by
# infra/scripts/install-desktop-stack.sh and run through the narrow sudoers
# rule (infra/sudoers.d/agenticenv-stack), which names each allowed profile
# explicitly. Paths are hardcoded on purpose: nothing here is taken from the
# caller's environment. Validation (sha256, VRAM budget, ctx_size) already
# happened when render-llama-env.sh produced the profile files.
set -euo pipefail

PROFILES_DIR=/etc/llm/profiles
ENV_LINK=/etc/llm/llama-server.env

profile="${1:-}"
if [[ ! "$profile" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "usage: agx-llm-use <profile>" >&2
  exit 2
fi
target="$PROFILES_DIR/$profile.env"
if [[ ! -f "$target" ]]; then
  echo "ERROR: $target not found. Render it: infra/scripts/render-llama-env.sh $profile" >&2
  exit 1
fi

link_value="profiles/$profile.env"
if [[ -L "$ENV_LINK" && "$(readlink "$ENV_LINK")" == "$link_value" ]] \
   && systemctl is-active --quiet llama-server.service; then
  echo "llama-server already on profile '$profile'"
  exit 0
fi

# Atomic swap: a half-written link must never be read by a (re)starting unit.
ln -sfn "$link_value" "$ENV_LINK.new"
mv -T "$ENV_LINK.new" "$ENV_LINK"
systemctl restart llama-server.service
echo "llama-server restarting on profile '$profile'"
