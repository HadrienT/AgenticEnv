source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
compile t -O2 -march=native "$H/test.cpp" && timeout 800 "$B/t" 2>"$B/err" || true
grep -m8 -E 'got |exception|bias' "$B/err" | cut -c1-200
