#!/bin/bash
# Stop hook: the agent may not end its turn on code it has not built since its last edit,
# because that code goes to the real repository. Denied a few times at most: a project
# with no build of its own must not hold the agent forever.
set -uo pipefail

max_denials=3
cat >/dev/null

cd "${OPENHANDS_PROJECT_DIR:-.}" || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
# shellcheck source=green_tree.sh
source "$(dirname "${BASH_SOURCE[0]}")/green_tree.sh"

base="$GREEN_REF"
git rev-parse -q --verify "$base" >/dev/null || base="$BASELINE_REF"
git rev-parse -q --verify "$base" >/dev/null || exit 0
tree="$(project_tree)" || exit 0
code='\.(c|cc|cpp|cxx|cu|h|hh|hpp|hxx|ipp|py|rs|go|ts|tsx|js)$|(^|/)(CMakeLists\.txt|Makefile)$'
changed="$(git diff --name-only "$base" "$tree" | grep -E "$code")" || exit 0

counter="$(git rev-parse --git-path agenticenv-stop-denials)"
denials="$(cat "$counter" 2>/dev/null || echo 0)"
[[ "$denials" -lt "$max_denials" ]] || exit 0
echo $((denials + 1)) >"$counter"

reason="You cannot finish yet. No build or test run has succeeded since you changed: $(echo "$changed" | head -10 | paste -sd' ')."
reason+=" Build the whole project and run its tests, in one command without a pipe or ';', so that the exit code is theirs."
reason+=" Compiling a single file does not count. Fix what fails, then finish."
printf '{"decision": "deny", "reason": %s}\n' "$(printf '%s' "$reason" | jq -Rs .)"
exit 2
