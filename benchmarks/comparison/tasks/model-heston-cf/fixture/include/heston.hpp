#pragma once
namespace model {
struct Heston { double v0, kappa, theta, xi, rho; };
// European call under Heston with continuous rate r and dividend yield q, by Fourier
// methods, accurate to 1e-8 absolute over the whole domain described in the task.
double heston_call(double S, double K, double r, double q, double T, const Heston& h);
double heston_put(double S, double K, double r, double q, double T, const Heston& h);
}  // namespace model
