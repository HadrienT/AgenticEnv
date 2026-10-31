Implement `gpu_asian_multi` from include/multi_gpu.h in src/multi_gpu.cu with CUDA: a Monte Carlo pricer spreading one simulation over several GPUs. The header comments are the spec.

Target: two Tesla V100 (shared with another process, so at most 256 MiB of device buffers on each), CUDA 12.4, compiled by `nvcc -std=c++17 -ccbin g++-13 -O3` as in the Makefile. Use std::thread on the host, one per device. There is no library besides CUDA: write the random number generator yourself. On any failure in a worker thread, the call must raise an exception on the caller's thread and not hang.
