#include "heston.hpp"
#include <cmath>
#include <complex>
#include <vector>
namespace model {
using C = std::complex<double>;
static C cf(double u, double T, const Heston& h) { C i(0, 1), z(u, -.5), iz = i * z; C b = h.kappa - h.rho * h.xi * iz, d = std::sqrt(b * b + h.xi * h.xi * (iz + z * z)), g = (b - d) / (b + d), e = std::exp(-d * T); C A = h.kappa * h.theta / (h.xi * h.xi) * ((b - d) * T - 2.0 * std::log((1.0 - g * e) / (1.0 - g))), B = (b - d) / (h.xi * h.xi) * (1.0 - e) / (1.0 - g * e); return std::exp(A + B * h.v0); }
static double integral(double x, double T, const Heston& h) {
    static std::vector<double> nodes, wts;
    if (nodes.empty()) { const int N = 64; nodes.resize(N); wts.resize(N); for (int k = 0; k < N; k++) { double t = std::cos(M_PI * (k + .75) / (N + .5)), p, q; for (int it = 0; it < 100; it++) { double a = 1, b = 0; for (int j = 0; j < N; j++) { double c = b; b = a; a = ((2 * j + 1) * t * b - j * c) / (j + 1); } p = a; q = N * (t * a - b) / (t * t - 1); t -= p / q; } nodes[k] = t; wts[k] = 2 / ((1 - t * t) * q * q); } }
    auto panel = [&](double a, double b) { double s = 0; for (size_t k = 0; k < nodes.size(); k++) { double u = .5 * (b - a) * nodes[k] + .5 * (a + b); s += wts[k] * (std::exp(C(0, 1) * u * x) * cf(u, T, h) / (u * u + .25)).real(); } return .5 * (b - a) * s; };
    double total = 0, a = 0, w = .5; for (int n = 0; n < 3000; n++) { double v = panel(a, a + w); total += v; a += w; if (n > 30 && std::fabs(v) < 1e-15) break; w *= 1.1; } return total; }
double heston_call(double S, double K, double r, double q, double T, const Heston& h) { double x = std::log(S / K) + (r - q) * T; return std::max(0.0, S * std::exp(-q * T) - std::sqrt(S * K * std::exp(-(r + q) * T)) / M_PI * integral(x, T, h)); }
double heston_put(double S, double K, double r, double q, double T, const Heston& h) { return std::max(0.0, heston_call(S, K, r, q, T, h) - S * std::exp(-q * T) + K * std::exp(-r * T)); }
}
