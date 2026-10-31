# Sourced by the quant-modeling checks, after lib.sh. Everything builds in the one tree that has
# a working incremental build; run.py restores it afterwards.
WORK=${AGX_BENCH_WORK:-$(cd "$LIB/../.." && pwd)/.work}
QM=$WORK/qm-base
VC=$QM/build/vcpkg_installed/x64-linux
# Only the files that differ from the base commit: ninja must not see the rest as new.
if [ "$P" != "$QM" ]; then
    SHA=$(cat "$WORK/qm-base-sha")
    git -C "$P" add -AN . >/dev/null 2>&1
    git -C "$P" diff --name-status --no-renames "$SHA" -- . ':(exclude)build' | while read -r st f; do
        if [ "$st" = D ]; then rm -f "$QM/$f"; else mkdir -p "$(dirname "$QM/$f")"; cp "$P/$f" "$QM/$f"; fi
    done
fi
qm_lib() { ( cd "$QM" && timeout 800 ninja -C build quantModeling >"$B/lib.log" 2>&1 ); local rc=$?; [ $rc -ne 0 ] && { echo "--- library build failed"; grep -m10 -E 'error|FAILED' "$B/lib.log" | cut -c1-220; }; return $rc; }
# qm_test <out> <sources...>: against the library just built, with GoogleTest.
qm_test() { local out=$1; shift; timeout 500 g++ -std=c++20 -O2 -DNDEBUG -I"$QM/include" -I"$LIB" -isystem "$VC/include" -isystem "$VC/include/eigen3" -DQM_PRODUCT_LIBRARY_DIR=\"$QM/api/app/product_library\" "$@" "$QM/build/libquantModeling.a" "$VC/lib/manual-link/libgtest_main.a" "$VC/lib/libgtest.a" -lpthread -o "$B/$out" 2>"$B/$out.err"; local rc=$?; [ $rc -ne 0 ] && { echo "--- test build failed"; grep -m10 -E 'error|undefined' "$B/$out.err" | cut -c1-220; }; return $rc; }
