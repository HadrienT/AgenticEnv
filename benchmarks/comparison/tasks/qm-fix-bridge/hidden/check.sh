source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/qm.sh"
if qm_lib; then echo "PASS library_builds"; else exit 0; fi
qm_test t "$H/test.cpp" && "$B/t" 2>"$B/err"; grep -m4 got "$B/err"
qm_test e "$QM/tests/testSimulationEngine.cpp" "$QM/tests/testSobolAndImportance.cpp" && timeout 400 "$B/e" --gtest_filter='Bridged*:SobolBridge*' >"$B/out" 2>&1 && echo "PASS existing_simulation_suite" || { echo "FAIL existing_simulation_suite"; grep -m5 FAILED "$B/out"; }
