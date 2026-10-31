source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
cd "$B"
ok=1
for f in "$P"/src/*.cpp; do g++ -std=c++20 -O1 -I"$P/include" -c "$f" -o "$B/$(basename "$f").o" 2>>"$B/lib.err" || ok=0; done
ar rcs "$B/liblib.a" "$B"/*.o 2>/dev/null
if [ $ok = 1 ] && g++ -std=c++20 -O1 -g -I"$P/include" -I"$LIB" "$H/test.cpp" "$B/liblib.a" -o "$B/t" 2>"$B/t.err"; then "$B/t" 2>/dev/null; echo "PASS library_not_rebuilt"; else grep -m6 -E 'error|undefined' "$B/lib.err" "$B/t.err" | cut -c1-220; echo "FAIL library_not_rebuilt"; fi
if grep -v '^ *//' "$P/include/acyclic.hpp" | grep -qwE 'Swap|Bond|NotionalVisitor'; then echo "FAIL header_has_no_concrete_trades"; else grep -q VisitableTrade "$P/include/acyclic.hpp" && echo "PASS header_has_no_concrete_trades" || echo "FAIL header_has_no_concrete_trades"; fi
grep -q 'dynamic_cast' "$P/include/acyclic.hpp" && ! grep -qE 'typeid|std::any|type_index' "$P/include/acyclic.hpp" && echo "PASS no_coupling" || echo "FAIL no_coupling"
