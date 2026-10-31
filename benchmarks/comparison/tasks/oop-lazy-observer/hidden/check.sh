source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
# Static library first, as the prompt says: the test executable links against it.
ok=1; for f in "$P"/src/*.cpp; do g++ -std=c++20 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all -I"$P/include" -c "$f" -o "$B/$(basename "$f").o" 2>>"$B/lib.err" || ok=0; done
ar rcs "$B/liblib.a" "$B"/*.o 2>/dev/null
if [ $ok = 1 ] && g++ -std=c++20 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all -I"$P/include" -I"$LIB" "$H/test.cpp" "$B/liblib.a" -o "$B/t" 2>"$B/t.err"; then "$B/t" 2>"$B/err"; grep -m6 -E 'ERROR: Addr|runtime error' "$B/err"|cut -c1-160; else grep -m6 -E 'error|undefined' "$B/lib.err" "$B/t.err" | cut -c1-220; fi
