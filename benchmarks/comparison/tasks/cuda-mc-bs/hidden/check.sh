source "$(dirname "${BASH_SOURCE[0]}")/../../_lib/lib.sh"
if gpu_compile t "$H/test.cpp"; then timeout 500 "$B/t" 2>"$B/err"; grep -m10 -E 'got |ratio|peak|leak|exception|s price' "$B/err"|cut -c1-160; else echo "FAIL compiles_with_nvcc"; fi
