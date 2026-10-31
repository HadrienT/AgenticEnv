#pragma once
struct McResult { double price; double std_error; unsigned long long paths; };
// Arithmetic Asian call under Black-Scholes, no dividend, average over S(t_i), t_i = i*T/n,
// i = 1..n, on CUDA device `device`. `paths` in the result is the number of paths actually
// used, and must equal nPaths. std_error is the standard error of the price.
McResult gpu_asian_call(double S, double K, double r, double sigma, double T, int n,
                        unsigned long long nPaths, unsigned int seed, int device);
