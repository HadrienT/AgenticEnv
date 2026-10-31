#pragma once
#include <cstdint>
namespace mc {
struct McResult { double price; double std_error; };
// Discretely monitored Asian call under Black-Scholes, continuous rate r and dividend
// yield q. The average is over the n dates t_i = i*T/n, i = 1..n; spot is not included.

// Exact value of the option on the geometric average.
double geometric_asian_call(double S0, double K, double r, double q, double sigma, double T, int n);

// Monte Carlo on the arithmetic average. With control_variate, use the geometric
// average option as control, with its exact value and an estimated coefficient.
// std_error is the standard error of the returned price.
McResult arithmetic_asian_call(double S0, double K, double r, double q, double sigma, double T, int n,
                               std::int64_t paths, std::uint64_t seed, bool control_variate);
}  // namespace mc
