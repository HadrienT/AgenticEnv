#include "iv.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
namespace model {
static double N(double x) { return .5 * std::erfc(-x * M_SQRT1_2); }
double bs_price(double S, double K, double r, double q, double s, double T, bool c) { double sq = s * std::sqrt(T), f = S * std::exp(-q * T), k = K * std::exp(-r * T), d1 = std::log(f / k) / sq + .5 * sq, d2 = d1 - sq; return c ? f * N(d1) - k * N(d2) : k * N(-d2) - f * N(-d1); }
double implied_vol(double p, double S, double K, double r, double q, double T, bool c) {
    double nan = std::numeric_limits<double>::quiet_NaN(); if (!std::isfinite(p) || !std::isfinite(S) || !std::isfinite(K) || !std::isfinite(T) || !std::isfinite(r) || !std::isfinite(q) || S <= 0 || K <= 0 || T <= 0 || p <= 0) return nan;
    double f = S * std::exp(-q * T), k = K * std::exp(-r * T); double low = std::max(c ? f - k : k - f, 0.0), up = c ? f : k; if (p <= low * (1 + 1e-15) || p >= up) return nan;
    double x = std::log(f / k), rt = std::sqrt(T), tv = p - low;  // work on the OTM time value, in log space
    auto otm = [&](double t) { double d1 = x / t + .5 * t; double fn = (c ? x >= 0 : x <= 0) ? 0 : 0; (void)fn; if (x >= 0) return k * N(-(d1 - t)) - f * N(-d1); return f * N(d1) - k * N(d1 - t); };
    double lo = std::log(1e-7), hi = std::log(120.0), y = std::log(std::max(std::fabs(x), 1e-3) + std::sqrt(2 * M_PI) * tv / f);
    y = std::clamp(y, lo, hi);
    for (int i = 0; i < 100; i++) { double t = std::exp(y), v = otm(t), e = std::log(std::max(v, 1e-300) / tv); if (e < 0) lo = y; else hi = y; double d1 = x / t + .5 * t, vg = f * std::exp(-.5 * d1 * d1) / std::sqrt(2 * M_PI), g = v > 0 ? vg * t / v : 0, ny = g > 0 ? y - e / g : .5 * (lo + hi); if (!(ny > lo && ny < hi)) ny = .5 * (lo + hi); bool done = std::fabs(ny - y) < 1e-13; y = ny; if (done) break; }
    double t = std::exp(y);
    return t / rt; }
}
