#include "sabr.hpp"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace model {
double sabr_vol(double F, double K, double T, const SabrParams& p) {
    double al = p.alpha, be = p.beta, rh = p.rho, nu = p.nu, lg = std::log(F / K), fk = std::pow(F * K, (1 - be) / 2), b2 = (1 - be) * (1 - be);
    double c = 1 + (b2 / 24 * al * al / (fk * fk) + rh * be * nu * al / (4 * fk) + (2 - 3 * rh * rh) / 24 * nu * nu) * T;
    double z = nu / al * fk * lg, zx; if (std::fabs(z) < 1e-7) zx = 1 - .5 * rh * z; else zx = z / std::log((std::sqrt(1 - 2 * rh * z + z * z) + z - rh) / (1 - rh));
    return al / (fk * (1 + b2 / 24 * lg * lg + b2 * b2 / 1920 * lg * lg * lg * lg)) * zx * c; }
SabrParams sabr_calibrate(double F, double T, double be, const std::vector<double>& K, const std::vector<double>& V) {
    if (K.size() < 3 || K.size() != V.size() || F <= 0 || T <= 0) throw std::invalid_argument("bad"); for (size_t i = 0; i < K.size(); i++) if (K[i] <= 0 || V[i] <= 0) throw std::invalid_argument("bad");
    double atm = V[0], d = 1e300; for (size_t i = 0; i < K.size(); i++) if (std::fabs(K[i] - F) < d) { d = std::fabs(K[i] - F); atm = V[i]; }
    auto obj = [&](const double* x) { SabrParams p{std::exp(x[0]), be, std::tanh(x[1]), std::exp(x[2])}; double e = 0; for (size_t i = 0; i < K.size(); i++) { double r = sabr_vol(F, K[i], T, p) - V[i]; e += r * r; } return e; };
    double best[3], bv = 1e300; double seedA = std::log(atm * std::pow(F, 1 - be));
    for (double r0 : {-.8, 0., .8}) for (double n0 : {-1.5, -.3, .5}) { double s[4][3] = {{seedA, r0, n0}, {seedA + .2, r0, n0}, {seedA, r0 + .4, n0}, {seedA, r0, n0 + .4}}, f[4]; for (int i = 0; i < 4; i++) f[i] = obj(s[i]);
        for (int it = 0; it < 1500; it++) { int w = 0, b = 0; for (int i = 1; i < 4; i++) { if (f[i] > f[w]) w = i; if (f[i] < f[b]) b = i; } double c[3] = {0, 0, 0}; for (int i = 0; i < 4; i++) if (i != w) for (int k = 0; k < 3; k++) c[k] += s[i][k] / 3; double r[3], e[3]; for (int k = 0; k < 3; k++) r[k] = 2 * c[k] - s[w][k]; double fr = obj(r); if (fr < f[b]) { for (int k = 0; k < 3; k++) e[k] = 3 * c[k] - 2 * s[w][k]; double fe = obj(e); if (fe < fr) { std::copy(e, e + 3, s[w]); f[w] = fe; } else { std::copy(r, r + 3, s[w]); f[w] = fr; } } else { int sw = 0; for (int i = 0; i < 4; i++) if (i != w && fr < f[i]) sw = 1; if (sw) { std::copy(r, r + 3, s[w]); f[w] = fr; } else { for (int k = 0; k < 3; k++) e[k] = .5 * (c[k] + s[w][k]); double fc = obj(e); if (fc < f[w]) { std::copy(e, e + 3, s[w]); f[w] = fc; } else for (int i = 0; i < 4; i++) if (i != b) { for (int k = 0; k < 3; k++) s[i][k] = .5 * (s[i][k] + s[b][k]); f[i] = obj(s[i]); } } } }
        for (int i = 0; i < 4; i++) if (f[i] < bv) { bv = f[i]; std::copy(s[i], s[i] + 3, best); } }
    return {std::exp(best[0]), be, std::clamp(std::tanh(best[1]), -.9999, .9999), std::exp(best[2])}; }
}
