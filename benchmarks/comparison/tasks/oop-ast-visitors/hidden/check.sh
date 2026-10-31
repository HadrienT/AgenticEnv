source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
compile t -O1 "$H/test.cpp" && "$B/t" || true
compile l -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all "$H/leak.cpp" && "$B/l" 2>/dev/null | grep PASS || echo "FAIL no_leaks_asan"
