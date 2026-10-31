source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/qm.sh"
( cd "$QM" && timeout 120 cmake --preset default >"$B/cfg.log" 2>&1 )
if qm_lib; then echo "PASS library_builds"; else exit 0; fi
qm_test t "$H/test.cpp" && "$B/t" 2>"$B/err"; grep -m6 got "$B/err"
qm_test e "$QM/tests/testDigital.cpp" "$QM/tests/testBSAna.cpp" && timeout 200 "$B/e" >"$B/out" 2>&1 && echo "PASS existing_digital_suite_still_passes" || { echo "FAIL existing_digital_suite_still_passes"; grep -m5 FAILED "$B/out"; }
if [ -f "$QM/tests/testGap.cpp" ] && grep -q 'testGap' "$QM/CMakeLists.txt" && [ "$(grep -c 'TEST(' "$QM/tests/testGap.cpp")" -ge 3 ]; then qm_test g "$QM/tests/testGap.cpp" && timeout 100 "$B/g" >"$B/o2" 2>&1 && echo "PASS repo_test_added" || echo "FAIL repo_test_added"; else echo "FAIL repo_test_added"; fi
