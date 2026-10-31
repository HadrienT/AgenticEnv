source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
compile t -O2 "$H/test.cpp" && timeout 300 "$B/t" || true
