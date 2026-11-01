#!/bin/bash
# PostToolUse hook (matcher: terminal): a build or test run that succeeded marks the tree
# as the last one known to work. require_green_build.sh and the iteration cap rely on it.
set -uo pipefail

input="$(cat)"
command="$(echo "$input" | jq -r '.tool_input.command // ""')"
exit_code="$(echo "$input" | jq -r '.tool_response.exit_code // -1')"
[[ "$exit_code" == 0 ]] || exit 0

# A pipe or `;` reports the exit code of another command than the build.
if [[ "$command" == *[\|\;]* && "$command" != *pipefail* ]]; then
  exit 0
fi
command="${command//make clean/}"
# Compiling one file proves nothing about the rest of the project.
if [[ "$command" =~ (g\+\+|gcc|clang\+\+|clang|nvcc)[[:space:]].*[[:space:]](-c|-fsyntax-only)([[:space:]]|$) ]]; then
  exit 0
fi
# The tool must be what runs, not a word on the line: `grep make Makefile` builds nothing.
build='(^|&&|;)[[:space:]]*([[:upper:]_]+=[^[:space:]]*[[:space:]]+)*'
build+='(make|ninja|ctest|pytest|cargo|nvcc|g\+\+|gcc|clang\+\+|clang|cmake[[:space:]]+--build'
build+='|npm[[:space:]]+(test|run[[:space:]]+build)|go[[:space:]]+(build|test)'
build+='|python3?[[:space:]]+-m[[:space:]]+pytest)([[:space:]]|$)'
[[ "$command" =~ $build ]] || exit 0

cd "${OPENHANDS_PROJECT_DIR:-.}" || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0
# shellcheck source=green_tree.sh
source "$(dirname "${BASH_SOURCE[0]}")/green_tree.sh"
tree="$(project_tree)" || exit 0
commit="$(git -c user.name=agenticenv -c user.email=agenticenv@local \
  commit-tree "$tree" -m "agenticenv green build")" || exit 0
git update-ref "$GREEN_REF" "$commit"
rm -f "$(git rev-parse --git-path agenticenv-stop-denials)"
exit 0
