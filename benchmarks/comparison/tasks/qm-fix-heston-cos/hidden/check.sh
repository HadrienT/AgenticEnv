source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/qm.sh"
if qm_lib; then echo "PASS library_builds"; else exit 0; fi
qm_test t "$H/test.cpp" && "$B/t" 2>"$B/err"; grep -m4 got "$B/err"
qm_test e "$QM/tests/testHestonCOS.cpp" && timeout 300 "$B/e" >"$B/out" 2>&1 && echo "PASS existing_cos_suite" || { echo "FAIL existing_cos_suite"; grep -m5 FAILED "$B/out"; }
