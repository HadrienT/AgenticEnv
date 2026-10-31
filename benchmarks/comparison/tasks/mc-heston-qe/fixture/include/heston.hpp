#pragma once
#include <cstdint>
namespace mc {
struct HestonParams { double S0, r, q, v0, kappa, theta, xi, rho; };
struct McResult { double price; double std_error; };
// European call by simulation over `steps` equal time steps.
McResult heston_call_mc(const HestonParams& p, double K, double T, int steps, std::int64_t paths, std::uint64_t seed);
// Monte Carlo estimate of E[S_T], with the same discretisation as heston_call_mc.
McResult heston_forward_mc(const HestonParams& p, double T, int steps, std::int64_t paths, std::uint64_t seed);
}  // namespace mc
