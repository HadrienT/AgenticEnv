#pragma once
#include <vector>
struct MultiResult {
    double price;
    double std_error;
    std::vector<unsigned long long> paths_per_device;  // same order as `devices`
};
// Arithmetic Asian call under Black-Scholes, r only, average over t_i = i*T/n, computed
// across all the CUDA devices listed, in parallel, in double precision. A given
// (nPaths, seed) gives the same price, to 1e-9, for any list of devices, including a
// device listed alone or in another order.
// Throws std::invalid_argument for an empty list, an index that does not exist, or a
// duplicated index, before doing any work.
MultiResult gpu_asian_multi(double S, double K, double r, double sigma, double T, int n,
                            unsigned long long nPaths, unsigned long long seed,
                            const std::vector<int>& devices);
