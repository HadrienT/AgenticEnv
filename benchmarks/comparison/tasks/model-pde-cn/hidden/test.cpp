#include "pde.hpp"
#include "chk.hpp"
using namespace model;
static double N(double x) { return .5 * erfc(-x * M_SQRT1_2); }
static double bsc(double S, double K, double r, double q, double v, double T) { double d1 = (log(S / K) + (r - q + .5 * v * v) * T) / (v * sqrt(T)); return S * exp(-q * T) * N(d1) - K * exp(-r * T) * N(d1 - v * sqrt(T)); }
int main() {
    sec("american_put_1", [] { return near(pde_price(Kind::AmericanPut, 36, 40, .06, 0, .2, 1, 400, 400).value, 4.4866, 1.5e-3); });
    sec("american_put_2_dividend", [] { return near(pde_price(Kind::AmericanPut, 100, 100, .05, .03, .3, 1, 400, 400).value, 10.7901, 1.5e-3); });
    sec("american_put_3_long", [] { return near(pde_price(Kind::AmericanPut, 100, 110, .08, 0, .2, 3, 800, 800).value, 12.2615, 3e-3); });
    sec("american_put_itm_exercise", [] { auto r = pde_price(Kind::AmericanPut, 80, 100, .02, .04, .25, .6, 400, 400); auto d = pde_price(Kind::AmericanPut, 40, 100, .08, 0, .2, 1, 400, 400); return near(r.value, 21.6283, 1.5e-3) && near(d.value, 60, 1e-6) && near(d.delta, -1, 1e-3); });
    sec("european_call_second_order", [] { double w = bsc(100, 105, .03, .01, .25, 1); double a = fabs(pde_price(Kind::EuropeanCall, 100, 105, .03, .01, .25, 1, 200, 200).value - w), b = fabs(pde_price(Kind::EuropeanCall, 100, 105, .03, .01, .25, 1, 400, 400).value - w), c = fabs(pde_price(Kind::EuropeanCall, 100, 105, .03, .01, .25, 1, 800, 800).value - w); fprintf(stderr, "%g %g %g\n", a, b, c); return (a + b) / (b + c) > 2.5 && c < 1e-3; });
    sec("digital_accuracy", [] { double w = .49458109105322356, x = .3850121214365749; return near(pde_price(Kind::DigitalCall, 100, 100, .05, .02, .2, 1, 400, 400).value, w, 1e-3) && near(pde_price(Kind::DigitalCall, 95, 100, .03, 0, .3, .5, 400, 400).value, x, 1e-3); });
    sec("digital_second_order", [] { double w = .3850121214365749; double e[4]; int k = 0; for (int n : {100, 200, 400, 800}) e[k++] = fabs(pde_price(Kind::DigitalCall, 95, 100, .03, 0, .3, .5, n, n).value - w); fprintf(stderr, "%g %g %g %g\n", e[0], e[1], e[2], e[3]); return (e[0] + e[1]) / (e[2] + e[3]) > 6 && e[3] < 3e-4; });
    sec("digital_gamma_smooth", [] { double K = 100, T = .02, r = .03, v = .3; int n = 400, sign = 0; int flips = 0; double exact_prev = 0; for (double S = 96; S <= 104.01; S += .5) { double g = pde_price(Kind::DigitalCall, S, K, r, 0, v, T, n, n).gamma, h = .01; auto f = [&](double s) { double d2 = (log(s / K) + (r - .5 * v * v) * T) / (v * sqrt(T)); return exp(-r * T) * N(d2); }; double ex = (f(S + h) - 2 * f(S) + f(S - h)) / (h * h); if (fabs(g - ex) > .012 + .3 * fabs(ex)) { fprintf(stderr, "S %g gamma %g exact %g\n", S, g, ex); return false; } } (void)sign; (void)flips; (void)exact_prev; return true; });
    sec("put_call_grid_independent", [] { auto c = pde_price(Kind::EuropeanCall, 100, 105, .03, .01, .25, 1, 400, 400), p = pde_price(Kind::EuropeanPut, 100, 105, .03, .01, .25, 1, 400, 400); return near(c.value - p.value, 100 * exp(-.01) - 105 * exp(-.03), 5e-4) && near(c.delta - p.delta, exp(-.01), 5e-4); });
    sec("spot_not_on_grid", [] { double v = 0; for (double S : {50., 73.21, 99.99, 137.5, 200.}) { auto r = pde_price(Kind::EuropeanCall, S, 100, .03, 0, .2, 5, 400, 400); if (!near(r.value, bsc(S, 100, .03, 0, .2, 5), 5e-3)) return false; v += r.delta; } return v > 0; });
    return 0;
}
