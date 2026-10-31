#pragma once
#include <cstdint>
namespace mc {
struct McResult { double price; double std_error; };
// Bermudan put under Black-Scholes, no dividend: exercisable at t_i = i*T/steps, i = 1..steps.
// Longstaff-Schwartz least-squares Monte Carlo with polynomial basis of degree 3.
McResult american_put_lsm(double S0, double K, double r, double sigma, double T, int steps,
                          std::int64_t paths, std::uint64_t seed);
}  // namespace mc
