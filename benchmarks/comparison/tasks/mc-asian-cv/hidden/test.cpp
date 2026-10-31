#include "asian.hpp"
#include "chk.hpp"
#include <chrono>
#include <vector>
using namespace mc;
// Second parameter set: reference 100M path control-variate run, harness/references.json.
static const double G1 = 4.183852073278523, A1 = 4.427067378551918, G2 = 18.20049810733757, A2 = 19.990021320566754;
// With fixings 73 days apart, QuantLib's analytic engine and the hand formula agree to 1e-14.
static const double G3 = 4.718231783699634;
static double ratio(bool cv) { std::vector<double> x; double se = 0; for (int s = 0; s < 40; s++) { auto r = arithmetic_asian_call(100, 105, .03, .01, .25, 1, 12, 20000, 1000 + s, cv); x.push_back(r.price); se += r.std_error / 40; } double m = 0, v = 0; for (double a : x) m += a / 40; for (double a : x) v += (a - m) * (a - m) / 39; double r = std::sqrt(v) / se; fprintf(stderr, "ratio %.3f\n", r); return r; }
int main() {
    sec("geo_closed_form", [] { return near(geometric_asian_call(100, 105, .03, .01, .25, 1, 12), G1, 1e-9) && near(geometric_asian_call(100, 105, .03, .01, .25, 1, 5), G3, 1e-9); });
    sec("geo_closed_form_2", [] { return near(geometric_asian_call(100, 90, .05, 0, .4, 2, 24), G2, 1e-9); });
    sec("plain_mc_unbiased", [] { auto r = arithmetic_asian_call(100, 105, .03, .01, .25, 1, 12, 2000000, 7, false); return near(r.price, A1, 4.5 * r.std_error) && r.std_error < .02; });
    sec("cv_mc_unbiased", [] { auto r = arithmetic_asian_call(100, 105, .03, .01, .25, 1, 12, 2000000, 8, true); return near(r.price, A1, 4.5 * r.std_error + 1e-4); });
    sec("cv_mc_unbiased_2", [] { auto r = arithmetic_asian_call(100, 90, .05, 0, .4, 2, 24, 2000000, 9, true); return near(r.price, A2, 4.5 * r.std_error + 1e-3); });
    sec("variance_reduction", [] { auto a = arithmetic_asian_call(100, 105, .03, .01, .25, 1, 12, 500000, 3, false), b = arithmetic_asian_call(100, 105, .03, .01, .25, 1, 12, 500000, 3, true); fprintf(stderr, "se ratio %.2f\n", a.std_error / b.std_error); return a.std_error / b.std_error > 10; });
    sec("se_is_honest_plain", [] { double r = ratio(false); return r > .65 && r < 1.4; });
    sec("se_is_honest_cv", [] { double r = ratio(true); return r > .65 && r < 1.4; });
    sec("seed_reproducible", [] { auto a = arithmetic_asian_call(100, 100, .02, 0, .2, 1, 12, 10000, 5, true), b = arithmetic_asian_call(100, 100, .02, 0, .2, 1, 12, 10000, 5, true); return a.price == b.price && a.std_error == b.std_error; });
    sec("seed_changes_result", [] { auto a = arithmetic_asian_call(100, 100, .02, 0, .2, 1, 12, 10000, 5, false), b = arithmetic_asian_call(100, 100, .02, 0, .2, 1, 12, 10000, 6, false); return a.price != b.price; });
    sec("speed", [] { auto t = std::chrono::steady_clock::now(); arithmetic_asian_call(100, 100, .02, 0, .2, 1, 12, 1000000, 5, true); double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t).count(); fprintf(stderr, "%.2fs\n", s); return s < 1.0; });
    return 0;
}
