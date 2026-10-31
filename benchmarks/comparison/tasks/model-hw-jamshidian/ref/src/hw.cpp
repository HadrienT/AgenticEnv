#include "hw.hpp"
#include <algorithm>
#include <cmath>
namespace model {
static double N(double x) { return .5 * std::erfc(-x * M_SQRT1_2); }
HullWhite::HullWhite(double a, double s, std::function<double(double)> p) : a_(a), s_(s), p_(std::move(p)) {}
double HullWhite::zcb(double t, double T, double r) const { double B = (1 - std::exp(-a_ * (T - t))) / a_, e = 1e-4; double lo = std::max(t - e, 0.0), f = -(std::log(p_(t + e)) - std::log(p_(lo))) / (t + e - lo); return p_(T) / p_(t) * std::exp(B * f - s_ * s_ / (4 * a_) * (1 - std::exp(-2 * a_ * t)) * B * B - B * r); }
double HullWhite::zcb_call(double K, double T, double S) const { double sp = s_ * std::sqrt((1 - std::exp(-2 * a_ * T)) / (2 * a_)) * (1 - std::exp(-a_ * (S - T))) / a_, h = std::log(p_(S) / (p_(T) * K)) / sp + sp / 2; return p_(S) * N(h) - K * p_(T) * N(h - sp); }
double HullWhite::zcb_put(double K, double T, double S) const { double sp = s_ * std::sqrt((1 - std::exp(-2 * a_ * T)) / (2 * a_)) * (1 - std::exp(-a_ * (S - T))) / a_, h = std::log(p_(S) / (p_(T) * K)) / sp + sp / 2; return K * p_(T) * N(sp - h) - p_(S) * N(-h); }
double HullWhite::swaption(bool payer, double T0, int n, double tau, double K) const { auto val = [&](double r) { double s = 0; for (int i = 1; i <= n; i++) s += (K * tau + (i == n)) * zcb(T0, T0 + i * tau, r); return s - 1; }; double lo = -1, hi = 1; for (int i = 0; i < 200; i++) { double m = .5 * (lo + hi); if (val(m) > 0) lo = m; else hi = m; } double r = .5 * (lo + hi), t = 0; for (int i = 1; i <= n; i++) { double c = K * tau + (i == n), X = zcb(T0, T0 + i * tau, r); t += c * (payer ? zcb_put(X, T0, T0 + i * tau) : zcb_call(X, T0, T0 + i * tau)); } return t; }
double HullWhite::forward_swap_rate(double T0, int n, double tau) const { double a = 0; for (int i = 1; i <= n; i++) a += tau * p_(T0 + i * tau); return (p_(T0) - p_(T0 + n * tau)) / a; }
}
