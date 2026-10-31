source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
compile t -O1 "$H/test.cpp" && "$B/t" || true
compile a -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all "$H/asan.cpp" && "$B/a" | grep PASS || echo "FAIL asan_clean"
