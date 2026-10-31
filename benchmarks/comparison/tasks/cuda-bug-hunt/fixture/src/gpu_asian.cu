#include "gpu_asian.h"
#include <cuda_runtime.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>

struct Tally { float sum; float sq; unsigned int count; };

__device__ inline unsigned int lcg(unsigned int& s) {
    s = s * 1664525u + 1013904223u;
    return s;
}
__device__ inline float gauss(unsigned int& s) {
    float u1 = lcg(s) * 2.3283064e-10f;
    float u2 = lcg(s) * 2.3283064e-10f;
    return sqrtf(-2.0f * logf(u1)) * cosf(6.2831855f * u2);
}

__global__ void asian_kernel(float S, float K, float drift, float vol, int n, unsigned int pathsPerThread,
                             unsigned int seed, Tally* tally) {
    unsigned int state = seed * 2654435761u + threadIdx.x;
    for (int i = 0; i < 16; i++) lcg(state);
    for (unsigned int p = 0; p < pathsPerThread; p++) {
        float x = 0, sum = 0;
        for (int k = 0; k < n; k++) {
            x += drift + vol * gauss(state);
            sum += S * expf(x);
        }
        float pay = sum / n - K;
        if (pay < 0) pay = 0;
        tally[0].sum += pay;
        tally[0].sq += pay * pay;
        tally[0].count += 1;
    }
}

McResult gpu_asian_call(double S, double K, double r, double sigma, double T, int n,
                        unsigned long long nPaths, unsigned int seed, int device) {
    cudaSetDevice(0);
    const int threads = 256;
    const int blocks = 2048;
    unsigned int pathsPerThread = nPaths / (blocks * threads);
    Tally* d;
    cudaMalloc(&d, sizeof(Tally) * 64 * 1024 * 1024 / sizeof(Tally));
    Tally zero = {0, 0, 0};
    cudaMemcpy(d, &zero, sizeof(Tally), cudaMemcpyHostToDevice);

    float dt = T / (n - 1);
    float drift = (r - 0.5 * sigma * sigma) * dt, vol = sigma * sqrt(dt);
    asian_kernel<<<blocks, threads>>>(S, K, drift, vol, n, pathsPerThread, seed, d);

    Tally h;
    cudaMemcpy(&h, d, sizeof(Tally), cudaMemcpyDeviceToHost);
    double m = double(h.sum) / h.count;
    double v = double(h.sq) / h.count - m * m;
    double df = exp(-r * T);
    return {df * m, df * sqrt(v / h.count), h.count};
}
