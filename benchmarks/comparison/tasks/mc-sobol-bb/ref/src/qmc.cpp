#include "qmc.hpp"
#include <algorithm>
#include <cmath>
#include <random>
namespace mc {
namespace { struct St { int dim; std::uint32_t idx = 0; std::vector<std::uint32_t> V, x; }; }
static double inv(double p) { static const double a[] = {-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00}, b[] = {-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01}, c[] = {-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00}, d[] = {7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00};
    p = std::clamp(p, 1e-16, 1 - 1e-16); double q, r, x; if (p < .02425) { q = std::sqrt(-2 * std::log(p)); x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); } else if (p > 1 - .02425) { q = std::sqrt(-2 * std::log(1 - p)); x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1); } else { q = p - .5; r = q * q; x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1); }
    double e = .5 * std::erfc(-x * M_SQRT1_2) - p, u = e * std::sqrt(2 * M_PI) * std::exp(.5 * x * x); return x - u / (1 + .5 * x * u); }
struct Holder { int d; std::uint32_t i = 0; std::uint32_t V[32][32]; std::uint32_t x[32] = {}; };
static std::vector<Holder*> dummy;
static Holder* H(Sobol* s) { return *reinterpret_cast<Holder**>(s); }
Sobol::Sobol(int d) { auto* h = new Holder; h->d = d; for (int j = 0; j < d; j++) { if (j == 0) { for (int b = 0; b < 32; b++) h->V[0][b] = 1u << (31 - b); continue; } auto& q = SOBOL_DATA[j - 1]; for (int b = 0; b < q.s; b++) h->V[j][b] = q.m[b] << (31 - b); for (int b = q.s; b < 32; b++) { std::uint32_t v = h->V[j][b - q.s]; v ^= v >> q.s; for (int k = 1; k < q.s; k++) if ((q.a >> (q.s - 1 - k)) & 1) v ^= h->V[j][b - k]; h->V[j][b] = v; } } impl_ = h; }
void Sobol::next(double* out) { auto* h = static_cast<Holder*>(impl_); if (h->i > 0) { int c = __builtin_ctz(h->i); for (int j = 0; j < h->d; j++) h->x[j] ^= h->V[j][c]; } h->i++; for (int j = 0; j < h->d; j++) out[j] = h->x[j] / 4294967296.0; }
void brownian_bridge(const double* z, int n, double T, double* w) { double dt = T / n; w[n - 1] = std::sqrt(T) * z[0]; int k = 1; for (int step = n; step > 1; step /= 2) for (int l = 0; l < n; l += step) { int m = l + step / 2, r = l + step; double wl = l == 0 ? 0 : w[l - 1], wr = w[r - 1]; w[m - 1] = .5 * (wl + wr) + std::sqrt(step * dt / 4) * z[k++]; } }
McResult asian_rqmc(double S0, double K, double r, double sg, double T, int n, int pts, int reps, std::uint64_t seed, bool bb) {
    std::mt19937_64 g(seed); std::vector<double> u(n), z(n), w(n), res; double df = std::exp(-r * T), dt = T / n;
    for (int R = 0; R < reps; R++) { std::vector<std::uint32_t> sh(n); for (auto& s : sh) s = std::uint32_t(g()); Sobol sob(n); double sum = 0;
        for (int p = 0; p < pts; p++) { sob.next(u.data()); for (int k = 0; k < n; k++) { auto b = std::uint32_t(u[k] * 4294967296.0) ^ sh[k]; z[k] = inv((b + .5) / 4294967296.0); }
            if (bb) brownian_bridge(z.data(), n, T, w.data()); else { double s = 0; for (int k = 0; k < n; k++) { s += std::sqrt(dt) * z[k]; w[k] = s; } }
            double avg = 0; for (int k = 0; k < n; k++) avg += std::exp((r - .5 * sg * sg) * (k + 1) * dt + sg * w[k]); sum += std::max(S0 * avg / n - K, 0.0); }
        res.push_back(df * sum / pts); }
    double m = 0, v = 0; for (double x : res) m += x / reps; for (double x : res) v += (x - m) * (x - m) / (reps - 1); return {m, std::sqrt(v / reps)};
}
}
