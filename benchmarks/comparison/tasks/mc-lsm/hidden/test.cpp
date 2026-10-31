#include "lsm.hpp"
#include "chk.hpp"
#include <chrono>
#include <vector>
using namespace mc;
static double N(double x) { return .5 * erfc(-x * M_SQRT1_2); }
// Bermudan with 50 dates by a refined CRR tree: 4.4778, matching the 4.478 of Longstaff-Schwartz's table 1.
static const double B1 = 4.477834062707482, B2 = 8.499437802963238, B3 = 1.1098885998672665;
int main() {
    sec("ls_table_itm", [] { auto r = american_put_lsm(36, 40, .06, .2, 1, 50, 200000, 3); return near(r.price, B1, .03); });
    sec("ls_table_high_vol", [] { auto r = american_put_lsm(36, 40, .06, .4, 2, 50, 200000, 4); return near(r.price, B2, .05); });
    sec("ls_table_otm", [] { auto r = american_put_lsm(44, 40, .06, .2, 1, 50, 200000, 5); return near(r.price, B3, .025); });
    sec("above_european", [] { double S = 36, K = 40, r = .06, v = .2, T = 1, d1 = (log(S / K) + (r + .5 * v * v) * T) / (v * sqrt(T)); double eu = K * exp(-r * T) * N(-(d1 - v * sqrt(T))) - S * N(-d1); return american_put_lsm(36, 40, .06, .2, 1, 50, 100000, 6).price > eu + .3; });
    sec("deep_itm_floor", [] { return american_put_lsm(10, 40, .06, .2, 1, 50, 50000, 7).price >= 30 - 1e-9; });
    sec("no_exercise_value", [] { auto r = american_put_lsm(400, 40, .06, .2, 1, 20, 20000, 8); return std::isfinite(r.price) && r.price >= 0 && r.price < 1e-6 && std::isfinite(r.std_error); });
    sec("se_is_honest", [] { std::vector<double> x; double se = 0; for (int s = 0; s < 30; s++) { auto r = american_put_lsm(36, 40, .06, .2, 1, 25, 20000, 100 + s); x.push_back(r.price); se += r.std_error / 30; } double m = 0, v = 0; for (double a : x) m += a / 30; for (double a : x) v += (a - m) * (a - m) / 29; double k = std::sqrt(v) / se; fprintf(stderr, "ratio %.2f\n", k); return k > .55 && k < 1.6; });
    sec("basis_not_ill_conditioned", [] { auto a = american_put_lsm(36000, 40000, .06, .2, 1, 50, 200000, 3), b = american_put_lsm(.0036, .004, .06, .2, 1, 50, 200000, 3); return near(a.price / 1000, B1, .05) && near(b.price * 10000, B1, .05); });
    sec("speed", [] { auto t = std::chrono::steady_clock::now(); american_put_lsm(36, 40, .06, .2, 1, 50, 100000, 9); double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t).count(); fprintf(stderr, "%.2fs\n", s); return s < 3; });
    return 0;
}
