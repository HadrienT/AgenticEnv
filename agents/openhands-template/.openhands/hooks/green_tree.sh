# Sourced by the green build hooks. A separate index: the agent's staging stays untouched.
GREEN_REF=refs/agenticenv/green
BASELINE_REF=refs/agenticenv/baseline

project_tree() {
  local index
  index="$(git rev-parse --git-path agenticenv-index)" || return 1
  GIT_INDEX_FILE="$index" git add -A >/dev/null 2>&1 && GIT_INDEX_FILE="$index" git write-tree
}
