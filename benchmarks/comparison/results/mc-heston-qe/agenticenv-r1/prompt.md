Implement include/heston.hpp in src/heston.cpp, in C++20 with the standard library only: Monte Carlo simulation of the Heston model that stays accurate at coarse time steps, in the hard regimes where the Feller condition is badly violated (for instance kappa = 0.5, theta = 0.04, xi = 1, rho = -0.9, with T = 10 and 8 steps per year). Euler is not good enough there.

The asset must also stay a martingale: E[S_T] must match the forward within Monte Carlo error at those coarse steps, including when kappa is small and xi is large.

Performance target: 1 million paths with 80 steps in at most 20 seconds on one thread.
