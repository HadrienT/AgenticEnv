#include "gpu_asian.h"
#include <cuda_runtime.h>
#include <math.h>
#include <stdint.h>
struct Acc { double s, q; };
__device__ inline uint64_t mix(uint64_t z) { z += 0x9e3779b97f4a7c15ULL; z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL; z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL; return z ^ (z >> 31); }
__global__ void kern(double S, double K, double dr, double vl, int n, uint64_t first, uint64_t count, uint64_t key, Acc* out) {
    uint64_t tid = uint64_t(blockIdx.x) * blockDim.x + threadIdx.x, per = gridDim.x * uint64_t(blockDim.x), c = count / per + (tid < count % per ? 1 : 0), st = first + tid * (count / per) + (tid < count % per ? tid : count % per); double s = 0, q = 0;
    for (uint64_t i = 0; i < c; i++) { uint64_t r = mix(key ^ (st + i)); double x = 0, sum = 0; for (int k = 0; k < n; k++) { r = mix(r); uint64_t r2 = mix(r); r = r2; double u1 = ((r >> 11) + .5) / 9007199254740992.0; r = mix(r); double u2 = ((r >> 11) + .5) / 9007199254740992.0, z = sqrt(-2 * log(u1)) * cos(6.283185307179586 * u2); x += dr + vl * z; sum += S * exp(x); } double p = sum / n - K; if (p < 0) p = 0; s += p; q += p * p; } out[tid].s = s; out[tid].q = q; }
McResult gpu_asian_call(double S, double K, double r, double sg, double T, int n, unsigned long long N, unsigned int seed, int device) {
    cudaSetDevice(device); const int B = 256, G = 1024; size_t bytes = sizeof(Acc) * B * G; Acc* d; cudaMalloc(&d, bytes); Acc* h = new Acc[B * G]; double dt = T / n, dr = (r - .5 * sg * sg) * dt, vl = sg * sqrt(dt), ss = 0, qq = 0; unsigned long long done = 0, batch = 256ULL * 1024 * 400; uint64_t key = uint64_t(seed) * 0x9e3779b97f4a7c15ULL + 1;
    while (done < N) { unsigned long long c = N - done < batch ? N - done : batch; kern<<<G, B>>>(S, K, dr, vl, n, done, c, key, d); cudaMemcpy(h, d, bytes, cudaMemcpyDeviceToHost); for (int i = 0; i < B * G; i++) { ss += h[i].s; qq += h[i].q; } done += c; }
    cudaFree(d); delete[] h; double m = ss / N, v = (qq / N - m * m), df = exp(-r * T); return {df * m, df * sqrt(fmax(v, 0.0) / N), N}; }
