# Sourced by every check.sh: P project, B scratch dir, H hidden dir.
P=$1; B=$2; H=$3
LIB=$(dirname "${BASH_SOURCE[0]}")
fail_all() { for n in "$@"; do echo "FAIL $n"; done; }
# compile <out> <extra flags...> ; sources: $P/src/*.cpp plus whatever is passed.
compile() {
    local out=$1; shift
    timeout 400 g++ -std=c++20 -I"$P/include" -I"$LIB" -pthread "$@" $(ls "$P"/src/*.cpp 2>/dev/null) -o "$B/$out" 2>"$B/$out.err"
    local rc=$?
    [ $rc -ne 0 ] && { echo "--- compile error ($out)"; grep -m12 -E 'error|undefined' "$B/$out.err" | cut -c1-240; }
    return $rc
}
# gpu_compile <out> <extra...>: nvcc with g++-13, as quant-modeling's CUDA preset does.
gpu_compile() {
    local out=$1; shift
    timeout 400 nvcc -std=c++17 -ccbin g++-13 -O3 -I"$P/include" -I"$LIB" "$@" $(ls "$P"/src/*.cu "$P"/src/*.cpp 2>/dev/null) -o "$B/$out" 2>"$B/$out.err"
    local rc=$?
    [ $rc -ne 0 ] && { echo "--- nvcc error ($out)"; grep -m12 -E 'error|undefined' "$B/$out.err" | cut -c1-240; }
    return $rc
}
