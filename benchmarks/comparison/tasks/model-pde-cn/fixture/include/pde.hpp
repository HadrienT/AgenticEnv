#pragma once
namespace model {
struct PdeResult { double value, delta, gamma; };
enum class Kind { EuropeanCall, EuropeanPut, AmericanPut, DigitalCall };
// Black-Scholes PDE in log-spot, Crank-Nicolson on nS space and nT time points.
// DigitalCall pays 1 if S_T > K. The spot need not be a grid point.
PdeResult pde_price(Kind kind, double S, double K, double r, double q, double sigma, double T, int nS, int nT);
}  // namespace model
