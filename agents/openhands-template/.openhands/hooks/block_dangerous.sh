#!/bin/bash
# PreToolUse hook (matcher: terminal) — hard, unconditional block on commands
# that would violate the human-approval policy from blueprint/06-CONFIG.md §5
# and blueprint/05-SEQUENCES.md §8, regardless of the session's confirmation
# mode. This is the ONLY structural defense against `--headless`'s forced
# always-approve behavior (confirmed: docs.openhands.dev/openhands/usage/cli/headless
# — headless cannot use --llm-approve and always auto-approves every action).
#
# Do not weaken this script to "ask for confirmation instead" — headless mode
# cannot ask. Denying unconditionally is the point.
set -euo pipefail

input="$(cat)"
command="$(echo "$input" | jq -r '.tool_input.command // ""')"

deny() {
  printf '{"decision": "deny", "reason": %s}\n' "$(printf '%s' "$1" | jq -Rs .)"
  exit 2
}

# git push (any form, any remote/branch/flags)
if [[ "$command" =~ git[[:space:]]+push ]]; then
  deny "git push is blocked by policy — a human must run it outside OpenHands."
fi

# git merge (fast-forward or not) and rebase onto shared history
if [[ "$command" =~ git[[:space:]]+(merge|rebase) ]]; then
  deny "git merge/rebase is blocked by policy — a human must run it outside OpenHands."
fi

# force flags on any git command (push -f, push --force, checkout -f, ...)
if [[ "$command" =~ git[[:space:]].*(--force|-f[[:space:]]) ]]; then
  deny "Force git operations are blocked by policy."
fi

# git reset --hard / clean -fd (destroys uncommitted work)
if [[ "$command" =~ git[[:space:]]+reset[[:space:]]+--hard ]] || [[ "$command" =~ git[[:space:]]+clean[[:space:]]+-[a-z]*f ]]; then
  deny "Destructive git operations (reset --hard / clean -f) are blocked by policy."
fi

# mass deletion outside a scratch dir
if [[ "$command" =~ rm[[:space:]]+-[a-z]*r[a-z]*f|rm[[:space:]]+-[a-z]*f[a-z]*r ]]; then
  deny "Recursive force-delete (rm -rf) is blocked by policy."
fi

# secret/credential files
if [[ "$command" =~ (\.ssh/|\.env[^.]|/etc/shadow|id_rsa) ]]; then
  deny "Access to secret/credential paths is blocked by policy."
fi

exit 0
