Implement `gpu_bs_call` from include/gpu_mc.h in src/gpu_mc.cu with CUDA: a Monte Carlo pricer running on the GPU.

Target: Tesla V100 (16 GB, shared with another process, so use at most 256 MiB of device buffers), CUDA 12.4, compiled by `nvcc -std=c++17 -ccbin g++-13 -O3` as in the Makefile. There is no library besides CUDA itself: write the random number generator yourself, and do not use CUDA Random.

It must work for path counts from 1 up to at least 2 billion in a single call (2 billion paths in under 40 seconds), without storing paths. Results must be statistically sound, must not depend on how the work is divided into batches or on the device used, and memory must not leak across calls.
