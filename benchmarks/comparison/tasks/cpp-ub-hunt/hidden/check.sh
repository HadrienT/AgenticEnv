source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
compile t -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all "$H/test.cpp" && ASAN_OPTIONS=detect_stack_use_after_return=1 "$B/t" 2>"$B/t.err" || true
grep -m5 -E 'ERROR: Addr|runtime error' "$B/t.err" | cut -c1-140
if grep -l -E 'suppress|no_sanitize' -r "$P/src" "$P/include" >/dev/null 2>&1; then echo "--- sanitizer suppressed"; echo "FAIL data_race"; else
if compile r -O1 -g -fsanitize=thread "$H/race.cpp"; then setarch -R env TSAN_OPTIONS=halt_on_error=1 "$B/r" 2>/dev/null | grep -E 'PASS|FAIL' || echo "FAIL data_race"; else echo "FAIL data_race"; fi; fi
