#include "gpu_mc.h"
#include "chk.hpp"
#include <cuda_runtime.h>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
static double N(double x) { return .5 * erfc(-x * M_SQRT1_2); }
static double bs(double S, double K, double r, double q, double v, double T) { double d1 = (log(S / K) + (r - q + .5 * v * v) * T) / (v * sqrt(T)); return S * exp(-q * T) * N(d1) - K * exp(-r * T) * N(d1 - v * sqrt(T)); }
static long app_mib() { char c[256]; snprintf(c, 256, "nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits | awk -F, '$1==%d{s+=$2} END{print s+0}'", getpid()); FILE* p = popen(c, "r"); long m = 0; if (p) { if (fscanf(p, "%ld", &m) != 1) m = 0; pclose(p); } return m; }
int main() {
    printf("PASS compiles_with_nvcc\n"); fflush(stdout);
    sec("price_is_right", [] { auto r = gpu_bs_call(100, 105, .03, .01, .25, 1.5, 200000000ULL, 12345, 1); return near(r.price, bs(100, 105, .03, .01, .25, 1.5), 4.5 * r.std_error) && r.std_error > 0; }, 60);
    sec("std_error_is_right", [] { double x[30], se = 0, m = 0, v = 0; for (int s = 0; s < 30; s++) { auto r = gpu_bs_call(100, 100, .02, 0, .2, 1, 5000000ULL, 100 + s, 1); x[s] = r.price; se += r.std_error / 30; m += x[s] / 30; } for (double a : x) v += (a - m) * (a - m) / 29; double k = std::sqrt(v) / se; fprintf(stderr, "ratio %.2f\n", k); return k > .65 && k < 1.4; }, 60);
    sec("seed_reproducible", [] { auto a = gpu_bs_call(100, 100, .02, 0, .2, 1, 3000000ULL, 9, 1), b = gpu_bs_call(100, 100, .02, 0, .2, 1, 3000000ULL, 9, 1); return a.price > 1 && a.price == b.price && a.std_error == b.std_error; }, 60);
    sec("seed_changes_result", [] { auto a = gpu_bs_call(100, 100, .02, 0, .2, 1, 3000000ULL, 9, 1), b = gpu_bs_call(100, 100, .02, 0, .2, 1, 3000000ULL, 10, 1); return a.price != b.price; }, 60);
    sec("small_path_counts", [] { bool ok = true; for (unsigned long long n : {1ULL, 2ULL, 3ULL, 7ULL, 1000ULL, 1025ULL, 65537ULL}) { auto r = gpu_bs_call(100, 100, .02, 0, .2, 1, n, 1, 1); if (!std::isfinite(r.price) || r.price < 0) ok = false; if (n >= 1000 && (r.std_error <= 0 || std::fabs(r.price - bs(100, 100, .02, 0, .2, 1)) > 5 * r.std_error + 1e-9)) ok = false; } return ok; }, 60);
    sec("two_billion_paths", [] { auto t = std::chrono::steady_clock::now(); auto r = gpu_bs_call(100, 100, .02, 0, .2, 1, 2200000000ULL, 77, 1); double d = std::chrono::duration<double>(std::chrono::steady_clock::now() - t).count(); fprintf(stderr, "%.1fs price %.6f se %.6f\n", d, r.price, r.std_error); double want = bs(100, 100, .02, 0, .2, 1), seWant = 14.1 / std::sqrt(2.2e9); return d < 60 && near(r.price, want, 5 * seWant) && r.std_error > .5 * seWant && r.std_error < 2 * seWant; }, 150);
    sec("vram_bounded", [] { std::atomic<bool> stop{false}; std::atomic<long> peak{0}; std::thread w([&] { while (!stop) { long m = app_mib(); if (m > peak) peak = m; std::this_thread::sleep_for(std::chrono::milliseconds(150)); } }); auto r = gpu_bs_call(100, 100, .02, 0, .2, 1, 1000000000ULL, 5, 1); stop = true; w.join(); fprintf(stderr, "peak %ld MiB\n", peak.load()); return r.price > 1 && peak < 900; }, 120);
    sec("no_vram_leak", [] { cudaSetDevice(1); size_t f0, f1, t; auto r = gpu_bs_call(100, 100, .02, 0, .2, 1, 100000ULL, 5, 1); if (r.price < 1) return false; cudaSetDevice(1); cudaMemGetInfo(&f0, &t); for (int i = 0; i < 300; i++) gpu_bs_call(100, 100, .02, 0, .2, 1, 1000ULL, i, 1); cudaSetDevice(1); cudaMemGetInfo(&f1, &t); fprintf(stderr, "leak %.1f MiB\n", (double(f0) - double(f1)) / 1048576); return double(f0) - double(f1) < 16e6; }, 120);
    sec("device_selection", [] { std::atomic<bool> stop{false}; std::string seen; std::thread w([&] { while (!stop) { char c[256]; snprintf(c, 256, "nvidia-smi --query-compute-apps=pid,gpu_uuid --format=csv,noheader | awk -F', ' '$1==%d{print $2}'", getpid()); FILE* p = popen(c, "r"); char b[128]; while (p && fgets(b, 128, p)) seen += b; if (p) pclose(p); std::this_thread::sleep_for(std::chrono::milliseconds(100)); } }); auto r = gpu_bs_call(100, 100, .02, 0, .2, 1, 3000000000ULL, 5, 0); stop = true; w.join(); FILE* q = popen("nvidia-smi -i 0 --query-gpu=uuid --format=csv,noheader", "r"), *q1 = popen("nvidia-smi -i 1 --query-gpu=uuid --format=csv,noheader", "r"); char u0[128] = "", u1[128] = ""; fgets(u0, 128, q); fgets(u1, 128, q1); pclose(q); pclose(q1); u0[strcspn(u0, "\n")] = 0; u1[strcspn(u1, "\n")] = 0; bool on0 = seen.find(u0) != std::string::npos, on1 = seen.find(u1) != std::string::npos; fprintf(stderr, "on0 %d on1 %d\n", on0, on1); return r.price > 1 && on0 && !on1; }, 90);
    sec("device_independent_result", [] { auto a = gpu_bs_call(100, 100, .02, 0, .2, 1, 40000000ULL, 123, 0), b = gpu_bs_call(100, 100, .02, 0, .2, 1, 40000000ULL, 123, 1); return a.price > 1 && near(a.price, b.price, 1e-9) && near(a.std_error, b.std_error, 1e-9); }, 60);
    return 0;
}
