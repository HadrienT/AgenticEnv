source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
compile t -O2 "$H/test.cpp" && timeout 200 "$B/t" || true
if compile ts -O1 -g -fsanitize=thread "$H/tsan.cpp"; then setarch -R env TSAN_OPTIONS=halt_on_error=1 timeout 200 "$B/ts" 2>"$B/ts.err" | grep PASS || { echo "FAIL tsan_clean"; head -12 "$B/ts.err"|cut -c1-160; }; else echo "FAIL tsan_clean"; fi
