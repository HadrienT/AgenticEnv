Implement include/pde.hpp in src/pde.cpp, in C++20 with the standard library only: a finite-difference Black-Scholes solver.

Requirements:
- second-order convergence in both space and time, including for discontinuous payoffs, with no spurious oscillation of delta or gamma near the strike;
- early exercise for the American put solved properly (PSOR or a Brennan-Schwartz-type method, with a converged free boundary, not a simple max after the step);
- accurate to 1e-3 at nS = nT = 400 for maturities up to 5 years, spots from 50 to 200 with K = 100.
