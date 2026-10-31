Implement include/iv.hpp in src/iv.cpp, in C++20 with the standard library only: a robust implied volatility solver.

For every (sigma, T, K) with sigma in [0.01, 5], T in [1/365, 30] and moneyness |log(F/K)| up to 4*sigma*sqrt(T), `implied_vol(bs_price(...))` must return sigma to 1e-7 relative or better, as long as the option's time value exceeds about 1e-11 of spot. Wings with vega near zero and very small time values must work: a plain Newton iteration will not. One million calls must take under 2 seconds on one thread.
