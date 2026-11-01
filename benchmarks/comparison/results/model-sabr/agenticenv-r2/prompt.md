Implement include/sabr.hpp in src/sabr.cpp, in C++20 with the standard library only: the Hagan SABR implied volatility and its calibration. The header comments are the spec.

The function must be smooth at K = F (no division blow-up and no jump when K is a tiny relative distance from F) and when nu tends to 0. The calibration must work from any reasonable quote set, without an initial guess from the caller, and stay robust to noisy quotes.
