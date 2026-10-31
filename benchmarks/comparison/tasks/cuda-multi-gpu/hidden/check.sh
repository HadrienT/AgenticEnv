source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
if gpu_compile t "$H/test.cpp" -lpthread; then timeout 700 "$B/t" 2>"$B/err"; grep -m10 -E 'got |price|leak|one |exception' "$B/err"|cut -c1-160; else echo "FAIL compiles_with_nvcc"; fi
