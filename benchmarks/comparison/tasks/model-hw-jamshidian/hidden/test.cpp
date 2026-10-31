#include "hw.hpp"
#include "chk.hpp"
#include <random>
using namespace model;
static double curve(double t) { return std::exp(-.03 * t); }
static double steep(double t) { return std::exp(-(.01 * t + .004 * t * t / (1 + .1 * t))); }
int main() {
    double a = .05, s = .012; HullWhite h(a, s, curve);
    sec("zcb_time_zero_fits_curve", [&] { HullWhite k(a, s, steep); double h0 = 1e-4, f0 = (std::log(steep(h0)) - std::log(steep(0))) / -h0; return near(k.zcb(0, 7, f0), steep(7), 1e-5) && near(h.zcb(0, 3, .03), curve(3), 1e-7); });
    sec("zcb_conditional", [&] { return near(h.zcb(5, 10, .05), .7834686027616033, 2e-6); });
    sec("bond_call", [&] { return near(h.zcb_call(.8, 5, 10), .06308828880445783, 2e-9); });
    sec("bond_put", [&] { return near(h.zcb_put(.82, 2, 7), .00838403761257045, 2e-9); });
    sec("parity", [&] { return near(h.zcb_call(.8, 5, 10) - h.zcb_put(.8, 5, 10), curve(10) - .8 * curve(5), 1e-12); });
    sec("jamshidian_annual", [&] { return near(h.swaption(true, 5, 5, 1, .03), .035063407167435785, 1e-6); });
    sec("jamshidian_semiannual", [&] { return near(h.swaption(true, 2, 20, .5, .045), .0070100051677041055, 1e-6); });
    sec("receiver_payer_parity", [&] { double K = .03; double af = 0, T0 = 5; for (int i = 1; i <= 5; i++) af += curve(T0 + i); double value = curve(T0) - curve(T0 + 5) - K * af; return near(h.swaption(true, T0, 5, 1, K) - h.swaption(false, T0, 5, 1, K), value, 1e-7); });
    sec("atm_forward_rate", [&] { double T0 = 3, tau = .5; int n = 8; double af = 0; for (int i = 1; i <= n; i++) af += tau * curve(T0 + i * tau); double f = (curve(T0) - curve(T0 + n * tau)) / af; HullWhite k(a, s, steep); double af2 = 0; for (int i = 1; i <= n; i++) af2 += tau * steep(T0 + i * tau); double f2 = (steep(T0) - steep(T0 + n * tau)) / af2; return near(h.forward_swap_rate(T0, n, tau), f, 1e-12) && near(k.forward_swap_rate(T0, n, tau), f2, 1e-12) && near(k.swaption(true, T0, n, tau, f2), k.swaption(false, T0, n, tau, f2), 1e-8); });
    sec("short_rate_mc_consistency", [&] { HullWhite k(a, s, steep); double T = 3, S = 6, K = .8; auto ln = [&](double t) { return std::log(steep(t)); }; double e = 1e-4; auto f = [&](double t) { return -(ln(t + e) - ln(t - e)) / (2 * e); }; double r0 = f(1e-3); std::mt19937_64 g(3); std::normal_distribution<double> n; int N = 400000, st = 300; double dt = T / st; auto alpha = [&](double t) { double u = s / a * (1 - std::exp(-a * t)); return f(t) + .5 * u * u; }; double sum = 0, sq = 0; for (int p = 0; p < N; p++) { double x = 0, I = 0, sd = s * std::sqrt((1 - std::exp(-2 * a * dt)) / (2 * a)), m = std::exp(-a * dt); double t = 0; for (int i = 0; i < st; i++) { double r1 = x + alpha(t); double nx = x * m + sd * n(g); t += dt; I += .5 * (r1 + nx + alpha(t)) * dt; x = nx; } double r = x + alpha(T); double v = std::exp(-I) * std::max(k.zcb(T, S, r) - K, 0.0); sum += v; sq += v * v; } double mc = sum / N, se = std::sqrt((sq / N - mc * mc) / N), an = k.zcb_call(K, T, S); fprintf(stderr, "mc %.6f se %.6f an %.6f\n", mc, se, an); (void)r0; return near(mc, an, 5 * se + 3e-4); }, 200);
    return 0;
}
