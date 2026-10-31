source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
compile t -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all "$H/test.cpp" && "$B/t" 2>"$B/err" || true
grep -m6 -E 'ERROR: Addr|runtime error|got |^\{' "$B/err" | cut -c1-260
if cat "$P"/include/* "$P"/src/* | grep -v '^ *//' | grep -qE 'dynamic_cast|typeid|enum +(class +)?[A-Za-z]*[Tt]ype'; then echo "FAIL no_type_switch"; else [ -s "$P/include/instruments.hpp" ] && grep -q 'accept' "$P/include/instruments.hpp" && echo "PASS no_type_switch" || echo "FAIL no_type_switch"; fi
