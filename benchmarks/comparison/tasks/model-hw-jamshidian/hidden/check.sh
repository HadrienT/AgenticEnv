source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
compile t -O2 "$H/test.cpp" && timeout 500 "$B/t" 2>"$B/err" || true
grep -m8 -E 'got |exception' "$B/err" | cut -c1-200
