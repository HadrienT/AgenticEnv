#pragma once
struct McResult { double price; double std_error; };
// European call under Black-Scholes, simulated on the CUDA device `device`, double
// precision. std_error is the standard error of the returned price. The same (nPaths,
// seed) gives the same result on any device and on every call.
McResult gpu_bs_call(double S, double K, double r, double q, double sigma, double T,
                     unsigned long long nPaths, unsigned long long seed, int device);
