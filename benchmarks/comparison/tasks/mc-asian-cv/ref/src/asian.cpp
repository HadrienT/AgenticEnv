#include "asian.hpp"
#include <algorithm>
#include <cmath>
#include <random>
namespace mc {
static double N(double x) { return .5 * std::erfc(-x * M_SQRT1_2); }
double geometric_asian_call(double S, double K, double r, double q, double s, double T, int n) {
    double dt = T / n, mt = 0, c = 0; for (int i = 1; i <= n; i++) mt += i * dt / n;
    for (int i = 1; i <= n; i++) for (int j = 1; j <= n; j++) c += std::min(i, j) * dt;
    double mu = std::log(S) + (r - q - .5 * s * s) * mt, var = s * s * c / (double(n) * n), sd = std::sqrt(var), d1 = (mu - std::log(K) + var) / sd;
    return std::exp(-r * T) * (std::exp(mu + .5 * var) * N(d1) - K * N(d1 - sd));
}
McResult arithmetic_asian_call(double S, double K, double r, double q, double s, double T, int n, std::int64_t paths, std::uint64_t seed, bool cv) {
    std::mt19937_64 g(seed); std::normal_distribution<double> nd; double dt = T / n, dr = (r - q - .5 * s * s) * dt, vl = s * std::sqrt(dt), df = std::exp(-r * T);
    double sx = 0, sy = 0, sxx = 0, syy = 0, sxy = 0, m = double(paths);
    for (std::int64_t i = 0; i < paths; i++) { double x = 0, a = 0, l = 0; for (int k = 0; k < n; k++) { x += dr + vl * nd(g); a += std::exp(x); l += x; } double A = df * std::max(S * a / n - K, 0.0), G = df * std::max(S * std::exp(l / n) - K, 0.0); sx += A; sy += G; sxx += A * A; syy += G * G; sxy += A * G; }
    double vx = (sxx - sx * sx / m) / (m - 1), vy = (syy - sy * sy / m) / (m - 1), c = (sxy - sx * sy / m) / (m - 1);
    if (!cv) return {sx / m, std::sqrt(vx / m)};
    double b = c / vy; return {sx / m - b * (sy / m - geometric_asian_call(S, K, r, q, s, T, n)), std::sqrt(std::max(vx - c * c / vy, 0.0) / m)};
}
}
