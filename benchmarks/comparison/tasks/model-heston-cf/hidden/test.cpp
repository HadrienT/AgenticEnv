#include "heston.hpp"
#include "chk.hpp"
#include <chrono>
using namespace model;
// QuantLib AnalyticHestonEngine and an independent Gil-Pelaez integral agree to 1e-13 on all of these.
static bool c(double S, double K, double r, double q, double T, Heston h, double want, double tol = 2e-8) { return near(heston_call(S, K, r, q, T, h), want, tol); }
static double N(double x) { return .5 * erfc(-x * M_SQRT1_2); }
int main() {
    Heston a{.04, 1.5, .04, .5, -.7}, b{.04, .5, .04, 1.0, -.9};
    sec("standard_case", [&] { return c(100, 100, .02, .01, 1, a, 7.526116651503193); });
    sec("deep_itm_short", [&] { return c(100, 50, .02, 0, .2, a, 50.1996361250879); });
    sec("far_otm_tiny_value", [&] { double p = heston_call(100, 200, .02, 0, .4, Heston{.09, 2, .09, 1, -.8}); return p > 0 && near(p, 1.4785521401674152e-06, 2e-8); });
    sec("andersen_atm", [&] { return c(100, 100, 0, 0, 10, b, 13.084670136992312); });
    sec("andersen_wings", [&] { return c(100, 70, 0, 0, 10, b, 35.84976970383796) && c(100, 140, 0, 0, 10, b, .2957744357980179); });
    sec("low_mean_reversion_long", [&] { return c(100, 100, 0, 0, 15, Heston{.04, .3, .04, .9, -.5}, 16.64922292035864); });
    sec("thirty_years", [&] { return c(100, 130, .03, .01, 30, Heston{.04, 2, .05, .3, -.5}, 40.40767405020492) && c(100, 100, 0, 0, 5, Heston{.09, 1, .09, 1, -.3}, 21.795287742473523); });
    sec("one_day", [&] { return c(100, 100, .01, 0, 1 / 365., a, .4187095550976986); });
    sec("high_vol_of_vol_positive_rho", [&] { return c(100, 120, .01, 0, 29 / 365., Heston{.2, 5, .04, 2, .5}, .7395341583780242); });
    sec("put_call_parity", [&] { for (double K : {50., 80., 100., 150., 200.}) for (double T : {.05, 1., 10.}) { double cp = heston_call(100, K, .03, .01, T, a) - heston_put(100, K, .03, .01, T, a), f = 100 * exp(-.01 * T) - K * exp(-.03 * T); if (!near(cp, f, 1e-8)) return false; } return true; });
    sec("black_scholes_limit", [&] { double v = .2, T = 1, d1 = (.03 + .5 * v * v) / v, want = 100 * N(d1) - 100 * exp(-.03) * N(d1 - v); return near(heston_call(100, 100, .03, 0, 1, Heston{.04, 1, .04, 1e-4, 0}), want, 1e-6); });
    sec("speed", [&] { auto t = std::chrono::steady_clock::now(); volatile double s = 0; for (int i = 0; i < 2000; i++) s = s + heston_call(100, 60 + i * .05, .02, 0, .5 + i * .001, a); double d = std::chrono::duration<double>(std::chrono::steady_clock::now() - t).count(); fprintf(stderr, "%.3fs\n", d); return d < 4; });
    return 0;
}
