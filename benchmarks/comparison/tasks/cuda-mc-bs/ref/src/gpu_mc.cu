#include "gpu_mc.h"
#include <cuda_runtime.h>
#include <math.h>
#include <stdint.h>
// Philox-like counter-based 2x32 rounds would do; xorshift-free SplitMix64 hashed from (seed, path) keeps it stateless.
__device__ inline uint64_t mix(uint64_t z) { z += 0x9e3779b97f4a7c15ULL; z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL; z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL; return z ^ (z >> 31); }
struct Acc { double s, q; };
__global__ void kern(double S, double K, double dr, double vl, uint64_t first, uint64_t count, uint64_t seed, Acc* out) {
    uint64_t tid = uint64_t(blockIdx.x) * blockDim.x + threadIdx.x, per = gridDim.x * uint64_t(blockDim.x);
    uint64_t n = count / per + (tid < count % per ? 1 : 0), start = first + tid * (count / per) + (tid < count % per ? tid : count % per);
    double s = 0, q = 0, c1 = 0, c2 = 0; uint64_t key = mix(seed);
    for (uint64_t i = 0; i < n; i++) { uint64_t a = mix(key ^ (start + i)); uint64_t b = mix(a); double u1 = ((a >> 11) + 0.5) * (1.0 / 9007199254740992.0), u2 = ((b >> 11) + 0.5) * (1.0 / 9007199254740992.0); double z = sqrt(-2 * log(u1)) * cos(6.283185307179586 * u2), p = S * exp(dr + vl * z) - K; if (p < 0) p = 0; s += p; q += p * p; }
    (void)c1; (void)c2; out[tid].s = s; out[tid].q = q; }
McResult gpu_bs_call(double S, double K, double r, double q, double sg, double T, unsigned long long N, unsigned long long seed, int device) {
    cudaSetDevice(device); const int B = 256, G = 4096; size_t bytes = sizeof(Acc) * B * G; Acc* d; cudaMalloc(&d, bytes); Acc* h = new Acc[B * G]; double dr = (r - q - .5 * sg * sg) * T, vl = sg * sqrt(T), ss = 0, qq = 0; unsigned long long done = 0; const unsigned long long batch = 256ULL * 4096 * 2000;
    while (done < N) { unsigned long long c = N - done < batch ? N - done : batch; kern<<<G, B>>>(S, K, dr, vl, done, c, seed, d); cudaMemcpy(h, d, bytes, cudaMemcpyDeviceToHost); for (int i = 0; i < B * G; i++) { ss += h[i].s; qq += h[i].q; } done += c; }
    cudaFree(d); delete[] h; double m = ss / N, v = N > 1 ? (qq / N - m * m) * N / (N - 1) : 0, df = exp(-r * T); return {df * m, df * sqrt(fmax(v, 0.0) / N)}; }
