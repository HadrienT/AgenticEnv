#include "multi_gpu.h"
#include "chk.hpp"
#include <chrono>
#include <cuda_runtime.h>
#include <numeric>
#include <stdexcept>
static const double REF = 10.03939842661773;  // 20M path control-variate run: S=100 K=95 r=.02 s=.3 T=1 n=64, se 1.1e-4
int main() {
    printf("PASS compiles_with_nvcc\n"); fflush(stdout);
    sec("price_is_right", [] { auto r = gpu_asian_multi(100, 95, .02, .3, 1, 64, 100000000ULL, 1, {0, 1}); fprintf(stderr, "price %.5f se %.5f\n", r.price, r.std_error); return near(r.price, REF, 4.5 * r.std_error + 3e-4) && r.std_error > 0 && r.std_error < .01; }, 120);
    sec("same_on_any_device_set", [] { auto a = gpu_asian_multi(100, 95, .02, .3, 1, 64, 30000000ULL, 7, {0}), b = gpu_asian_multi(100, 95, .02, .3, 1, 64, 30000000ULL, 7, {1}), c = gpu_asian_multi(100, 95, .02, .3, 1, 64, 30000000ULL, 7, {0, 1}), d = gpu_asian_multi(100, 95, .02, .3, 1, 64, 30000000ULL, 7, {1, 0}); return near(a.price, b.price, 1e-9) && near(a.price, c.price, 1e-9) && near(a.price, d.price, 1e-9) && near(a.std_error, c.std_error, 1e-9); }, 120);
    sec("both_devices_used", [] { auto r = gpu_asian_multi(100, 95, .02, .3, 1, 64, 40000000ULL, 2, {0, 1}); return r.paths_per_device.size() == 2 && r.paths_per_device[0] > 8000000ULL && r.paths_per_device[1] > 8000000ULL; }, 60);
    sec("split_covers_all_paths", [] { bool ok = true; for (unsigned long long n : {1ULL, 3ULL, 1000001ULL}) { auto r = gpu_asian_multi(100, 95, .02, .3, 1, 8, n, 4, {0, 1}); if (std::accumulate(r.paths_per_device.begin(), r.paths_per_device.end(), 0ULL) != n || !std::isfinite(r.price)) ok = false; } return ok; }, 60);
    sec("faster_on_two_gpus", [] { auto run = [](std::vector<int> d) { auto t = std::chrono::steady_clock::now(); gpu_asian_multi(100, 95, .02, .3, 1, 64, 600000000ULL, 3, d); return std::chrono::duration<double>(std::chrono::steady_clock::now() - t).count(); }; double one = run({1}), two = run({0, 1}); fprintf(stderr, "one %.2f two %.2f\n", one, two); return two < one / 1.3; }, 180);
    sec("bad_device_throws", [] { auto bad = [](std::vector<int> d) { try { gpu_asian_multi(100, 95, .02, .3, 1, 8, 1000, 1, d); } catch (const std::invalid_argument&) { return true; } return false; }; return bad({}) && bad({99}) && bad({0, 0}) && bad({-1}); }, 30);
    sec("error_does_not_hang", [] { try { gpu_asian_multi(100, 95, .02, .3, 1, 8, 1000, 1, {0, 57}); } catch (const std::exception&) { return true; } return false; }, 30);
    sec("no_vram_leak", [] { gpu_asian_multi(100, 95, .02, .3, 1, 8, 10000ULL, 5, {1}); cudaSetDevice(1); size_t f0, f1, t; cudaMemGetInfo(&f0, &t); for (int i = 0; i < 40; i++) gpu_asian_multi(100, 95, .02, .3, 1, 8, 10000ULL, i, {1}); cudaSetDevice(1); cudaMemGetInfo(&f1, &t); fprintf(stderr, "leak %.1f\n", (double(f0) - double(f1)) / 1048576); return double(f0) - double(f1) < 16e6; }, 60);
    return 0;
}
