#include "pde.hpp"
#include <algorithm>
#include <cmath>
#include <vector>
namespace model {
PdeResult pde_price(Kind kd, double S, double K, double r, double q, double s, double T, int nS, int nT) {
    double L = std::max(6 * s * std::sqrt(T), 1.0) + std::fabs(std::log(S / K)); double dx = 2 * L / nS, x0 = -L; // grid on log(S/K), strike on a node, cell averaged payoff
    int M = nS + 1; std::vector<double> x(M), V(M), I(M); double xs = std::log(S / K);
    for (int i = 0; i < M; i++) x[i] = x0 + i * dx;
    auto avg = [&](double a, double b) { double h = (b - a) / 20, t = 0; for (int k = 0; k < 20; k++) { double y = a + (k + .5) * h, sv = K * std::exp(y); double p = 0; switch (kd) { case Kind::EuropeanCall: p = std::max(sv - K, 0.0); break; case Kind::EuropeanPut: case Kind::AmericanPut: p = std::max(K - sv, 0.0); break; case Kind::DigitalCall: p = y > 0 ? 1 : 0; break; } t += p; } return t / 20; };
    for (int i = 0; i < M; i++) { V[i] = avg(x[i] - .5 * dx, x[i] + .5 * dx); I[i] = std::max(K - K * std::exp(x[i]), 0.0); }
    double nu = r - q - .5 * s * s, A = .5 * s * s / (dx * dx), Bc = nu / (2 * dx), lo = A - Bc, di = -2 * A - r, up = A + Bc;
    bool am = kd == Kind::AmericanPut; double dt0 = T / nT;
    auto bound = [&](double t, bool low) { double sv = K * std::exp(low ? x[0] : x[M - 1]); switch (kd) { case Kind::EuropeanCall: return low ? 0.0 : sv * std::exp(-q * t) - K * std::exp(-r * t); case Kind::EuropeanPut: return low ? K * std::exp(-r * t) - sv * std::exp(-q * t) : 0.0; case Kind::AmericanPut: return low ? K - sv : 0.0; case Kind::DigitalCall: return low ? 0.0 : std::exp(-r * t); } return 0.0; };
    auto step = [&](double dt, double th, double tn) { std::vector<double> R(M), a(M), b(M), c(M), d(M); for (int i = 1; i < M - 1; i++) R[i] = V[i] + (1 - th) * dt * (lo * V[i - 1] + di * V[i] + up * V[i + 1]); double vl = bound(tn, true), vh = bound(tn, false);
        double aa = -th * dt * lo, bb = 1 - th * dt * di, cc = -th * dt * up;
        if (!am) { b[1] = bb; d[1] = R[1] - aa * vl; for (int i = 2; i < M - 1; i++) { double m = aa / b[i - 1]; b[i] = bb - m * cc; d[i] = R[i] - m * d[i - 1]; } d[M - 2] -= cc * vh; V[M - 2] = d[M - 2] / b[M - 2]; if (M > 3) { /*last eq carries vh*/ } for (int i = M - 3; i >= 1; i--) V[i] = (d[i] - cc * V[i + 1]) / b[i]; }
        else { for (int it = 0; it < 20000; it++) { double e = 0; V[0] = vl; V[M - 1] = vh; for (int i = 1; i < M - 1; i++) { double g = (R[i] - aa * V[i - 1] - cc * V[i + 1]) / bb; double nv = std::max(I[i], V[i] + 1.5 * (g - V[i])); e = std::max(e, std::fabs(nv - V[i])); V[i] = nv; } if (e < 1e-11) break; } }
        V[0] = vl; V[M - 1] = vh; };
    double t = 0; for (int k = 0; k < 4; k++) { t += dt0 / 2; step(dt0 / 2, 1.0, t); }
    for (int k = 2; k < nT; k++) { t += dt0; step(dt0, .5, t); }
    int i = std::clamp(int((xs - x0) / dx), 2, M - 4); double w[4], h = xs; std::vector<double> xx(x.begin() + i - 1, x.begin() + i + 3);
    // cubic lagrange in log-space
    double f = 0, f1 = 0, f2 = 0; for (int a = 0; a < 4; a++) { double p = 1, p1 = 0, p2 = 0; for (int b = 0; b < 4; b++) { if (b == a) continue; double dn = xx[a] - xx[b]; double n2 = p2 * (h - xx[b]) / dn + 2 * p1 / dn, n1 = p1 * (h - xx[b]) / dn + p / dn; p = p * (h - xx[b]) / dn; p1 = n1; p2 = n2; } f += p * V[i - 1 + a]; f1 += p1 * V[i - 1 + a]; f2 += p2 * V[i - 1 + a]; } (void)w;
    return {f, f1 / S, (f2 - f1) / (S * S)}; }
}
