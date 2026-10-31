#include "heston.hpp"
#include <algorithm>
#include <cmath>
#include <random>
namespace mc {
template <class F> static McResult sim(const HestonParams& p, double T, int st, std::int64_t N, std::uint64_t seed, F pay) {
    std::mt19937_64 g(seed); std::normal_distribution<double> nd; std::uniform_real_distribution<double> un;
    double dt = T / st, e = std::exp(-p.kappa * dt), g1 = .5, g2 = .5, psiC = 1.5;
    double k0 = -p.rho * p.kappa * p.theta / p.xi * dt, k1 = g1 * dt * (p.kappa * p.rho / p.xi - .5) - p.rho / p.xi, k2 = g2 * dt * (p.kappa * p.rho / p.xi - .5) + p.rho / p.xi, k3 = g1 * dt * (1 - p.rho * p.rho), k4 = g2 * dt * (1 - p.rho * p.rho);
    double A = k2 + .5 * k4, s = 0, ss = 0, drift = (p.r - p.q) * dt;
    for (std::int64_t i = 0; i < N; i++) { double v = p.v0, x = std::log(p.S0);
        for (int k = 0; k < st; k++) { double m = p.theta + (v - p.theta) * e, s2 = v * p.xi * p.xi * e * (1 - e) / p.kappa + p.theta * p.xi * p.xi * (1 - e) * (1 - e) / (2 * p.kappa), psi = s2 / (m * m), nv, K0s;
            double u = un(g);
            if (psi <= psiC) { double b2 = 2 / psi - 1 + std::sqrt(2 / psi) * std::sqrt(2 / psi - 1), a = m / (1 + b2), z = .5 * erfc(0); (void)z; double Z = nd(g); nv = a * (std::sqrt(b2) + Z) * (std::sqrt(b2) + Z); K0s = -A * b2 * a / (1 - 2 * A * a) + .5 * std::log(1 - 2 * A * a) - (k1 + .5 * k3) * v; }
            else { double pp = (psi - 1) / (psi + 1), beta = (1 - pp) / m; nv = u <= pp ? 0 : std::log((1 - pp) / (1 - u)) / beta; K0s = -std::log(pp + beta * (1 - pp) / (beta - A)) - (k1 + .5 * k3) * v; }
            (void)k0; x += drift + K0s + k1 * v + k2 * nv + std::sqrt(k3 * v + k4 * nv) * nd(g); v = nv; }
        double y = pay(std::exp(x)); s += y; ss += y * y; }
    double m = s / N; return {m, std::sqrt((ss - N * m * m) / (N - 1) / N)};
}
McResult heston_call_mc(const HestonParams& p, double K, double T, int st, std::int64_t N, std::uint64_t seed) { double d = std::exp(-p.r * T); return sim(p, T, st, N, seed, [=](double s) { return d * std::max(s - K, 0.0); }); }
McResult heston_forward_mc(const HestonParams& p, double T, int st, std::int64_t N, std::uint64_t seed) { return sim(p, T, st, N, seed, [](double s) { return s; }); }
}
