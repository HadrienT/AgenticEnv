Implement include/heston.hpp in src/heston.cpp, in C++20 with the standard library only: semi-analytic Heston European option prices.

It must be accurate to 1e-8 absolute over maturities from one day to 30 years, strikes from 50% to 200% of spot, xi up to 2, |rho| up to 0.9, and Feller-violating parameters. Prices of far out-of-the-money options as small as 1e-6 must be right, and a price must never be negative. No analytic continuation failures: the complex logarithm branch has to be handled correctly at long maturities. One price must take at most 2 ms on average.
