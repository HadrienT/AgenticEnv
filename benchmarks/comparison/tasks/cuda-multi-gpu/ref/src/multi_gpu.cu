#include "multi_gpu.h"
#include <cuda_runtime.h>
#include <math.h>
#include <stdint.h>
#include <exception>
#include <mutex>
#include <set>
#include <stdexcept>
#include <thread>
struct Acc { double s, q; };
__device__ inline uint64_t mix(uint64_t z) { z += 0x9e3779b97f4a7c15ULL; z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL; z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL; return z ^ (z >> 31); }
__global__ void kern(double S, double K, double dr, double vl, int n, uint64_t first, uint64_t count, uint64_t key, Acc* out) {
    uint64_t tid = uint64_t(blockIdx.x) * blockDim.x + threadIdx.x, per = gridDim.x * uint64_t(blockDim.x), c = count / per + (tid < count % per ? 1 : 0), st = first + tid * (count / per) + (tid < count % per ? tid : count % per); double s = 0, q = 0;
    for (uint64_t i = 0; i < c; i++) { uint64_t r = mix(key ^ (st + i)); double x = 0, sum = 0; for (int k = 0; k < n; k++) { r = mix(r); double u1 = ((r >> 11) + .5) / 9007199254740992.0; r = mix(r); double u2 = ((r >> 11) + .5) / 9007199254740992.0, z = sqrt(-2 * log(u1)) * cos(6.283185307179586 * u2); x += dr + vl * z; sum += S * exp(x); } double p = sum / n - K; if (p < 0) p = 0; s += p; q += p * p; } out[tid].s = s; out[tid].q = q; }
MultiResult gpu_asian_multi(double S, double K, double r, double sg, double T, int n, unsigned long long N, unsigned long long seed, const std::vector<int>& devs) {
    int cnt = 0; if (cudaGetDeviceCount(&cnt) != cudaSuccess) throw std::runtime_error("no cuda"); std::set<int> u(devs.begin(), devs.end()); if (devs.empty() || u.size() != devs.size()) throw std::invalid_argument("devices"); for (int d : devs) if (d < 0 || d >= cnt) throw std::invalid_argument("device");
    double dt = T / n, dr = (r - .5 * sg * sg) * dt, vl = sg * sqrt(dt), ss = 0, qq = 0; std::mutex m; std::exception_ptr err; std::vector<std::thread> w; std::vector<unsigned long long> per(devs.size(), 0); uint64_t key = seed * 0x9e3779b97f4a7c15ULL + 1; size_t D = devs.size();
    // Paths are cut in fixed chunks whatever the device list: the sum does not depend on it.
    const unsigned long long chunk = 1ULL << 22; const int B = 256, G = 1024; size_t bytes = sizeof(Acc) * B * G;
    for (size_t i = 0; i < D; i++) w.emplace_back([&, i] { try { if (cudaSetDevice(devs[i]) != cudaSuccess) throw std::runtime_error("device"); Acc* d; if (cudaMalloc(&d, bytes) != cudaSuccess) throw std::runtime_error("alloc"); std::vector<Acc> h(B * G); double ls = 0, lq = 0; unsigned long long used = 0; unsigned long long nch = (N + chunk - 1) / chunk; for (unsigned long long c = i; c < nch; c += D) { unsigned long long f = c * chunk, cn = N - f < chunk ? N - f : chunk; kern<<<G, B>>>(S, K, dr, vl, n, f, cn, key, d); cudaMemcpy(h.data(), d, bytes, cudaMemcpyDeviceToHost); for (auto& a : h) { ls += a.s; lq += a.q; } used += cn; } cudaFree(d); std::lock_guard<std::mutex> l(m); ss += ls; qq += lq; per[i] = used; } catch (...) { std::lock_guard<std::mutex> l(m); if (!err) err = std::current_exception(); } });
    for (auto& t : w) t.join(); if (err) std::rethrow_exception(err); double mean = ss / N, v = qq / N - mean * mean, df = exp(-r * T); return {df * mean, df * sqrt(fmax(v, 0.0) / N), per}; }
