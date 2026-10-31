#include "gpu_asian.h"
#include "chk.hpp"
#include <cuda_runtime.h>
// 80M path control-variate run in numpy: 6.15604580887 +- 2.7e-5.
static const double REF = 6.15604580887108;
int main() {
    printf("PASS compiles_with_nvcc\n"); fflush(stdout);
    sec("paths_accounted", [] { auto r = gpu_asian_call(100, 100, .05, .2, 1, 12, 100000000ULL, 3, 1); fprintf(stderr, "paths %llu\n", r.paths); return r.paths == 100000000ULL; }, 90);
    sec("remainder_paths", [] { bool ok = true; for (unsigned long long n : {1000003ULL, 1ULL, 4097ULL}) { auto r = gpu_asian_call(100, 100, .05, .2, 1, 12, n, 3, 1); if (r.paths != n || !std::isfinite(r.price)) ok = false; } return ok; }, 60);
    sec("blocks_independent", [] { double x[30], se = 0, m = 0, v = 0; for (int s = 0; s < 30; s++) { auto r = gpu_asian_call(100, 100, .05, .2, 1, 12, 2000000ULL, 100 + s, 1); x[s] = r.price; se += r.std_error / 30; m += x[s] / 30; } for (double a : x) v += (a - m) * (a - m) / 29; double k = std::sqrt(v) / se; fprintf(stderr, "ratio %.2f\n", k); return k > .65 && k < 1.4; }, 90);
    sec("no_nan_in_tails", [] { auto r = gpu_asian_call(100, 100, .05, .2, 1, 12, 1500000000ULL, 7, 1); fprintf(stderr, "price %.6f se %.6f\n", r.price, r.std_error); return std::isfinite(r.price) && std::isfinite(r.std_error); }, 120);
    sec("double_precision_accuracy", [] { auto r = gpu_asian_call(100, 100, .05, .2, 1, 12, 2000000000ULL, 8, 1); fprintf(stderr, "price %.6f se %.6f\n", r.price, r.std_error); return r.paths == 2000000000ULL && near(r.price, REF, 5 * r.std_error + 3e-4) && r.std_error < 3e-3 && r.std_error > 1e-4; }, 150);
    sec("average_dates", [] { auto r = gpu_asian_call(100, 100, .05, .2, 1, 12, 400000000ULL, 9, 1); return near(r.price, REF, 5 * r.std_error + .002); }, 90);
    sec("vram_no_leak", [] { gpu_asian_call(100, 100, .05, .2, 1, 12, 100000ULL, 5, 1); cudaSetDevice(1); size_t f0, f1, t; cudaMemGetInfo(&f0, &t); for (int i = 0; i < 40; i++) gpu_asian_call(100, 100, .05, .2, 1, 12, 10000ULL, i, 1); cudaSetDevice(1); cudaMemGetInfo(&f1, &t); fprintf(stderr, "leak %.1f MiB\n", (double(f0) - double(f1)) / 1048576); return double(f0) - double(f1) < 16e6; }, 60);
    sec("device_argument", [] { gpu_asian_call(100, 100, .05, .2, 1, 12, 10000ULL, 5, 1); int d = -1; cudaGetDevice(&d); gpu_asian_call(100, 100, .05, .2, 1, 12, 10000ULL, 5, 0); int e = -1; cudaGetDevice(&e); fprintf(stderr, "device %d %d\n", d, e); return d == 1 && e == 0; }, 30);
    return 0;
}
