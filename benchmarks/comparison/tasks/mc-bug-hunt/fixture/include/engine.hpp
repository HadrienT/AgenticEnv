#pragma once
#include <cstdint>
namespace mc {
struct Market { double S0, r, q, sigma; };
struct McResult { double price; double std_error; };
// European call, Black-Scholes with continuous dividend yield q.
// With antithetic, `paths` is the total number of simulated paths and std_error accounts
// for the correlation between the two members of a pair.
McResult european(const Market& m, double K, double T, bool is_call, std::int64_t paths, std::uint64_t seed, bool antithetic);
// Asian call on the arithmetic average of S(t_i), t_i = i*T/n, i = 1..n, S0 not included.
McResult asian(const Market& m, double K, double T, int n, std::int64_t paths, std::uint64_t seed);
// Down-and-out call, continuously monitored, simulated on `steps` steps with the
// Brownian-bridge survival probability between grid points.
McResult down_out_call(const Market& m, double K, double B, double T, int steps, std::int64_t paths, std::uint64_t seed);
// Cash-or-nothing call paying 1 if S_T > K, on several threads. The result must converge
// as paths grow, whatever `threads` is, and each thread must draw independent numbers.
McResult digital_mt(const Market& m, double K, double T, std::int64_t paths, std::uint64_t seed, int threads);
}  // namespace mc
