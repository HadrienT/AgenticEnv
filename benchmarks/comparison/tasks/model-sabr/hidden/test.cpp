#include "sabr.hpp"
#include "chk.hpp"
#include <random>
using namespace model;
static double smile(double F, double T, SabrParams p, std::vector<double> K, double noise, SabrParams& out, unsigned s = 1) { std::mt19937 g(s); std::normal_distribution<double> n; std::vector<double> v; for (double k : K) v.push_back(sabr_vol(F, k, T, p) + noise * n(g)); out = sabr_calibrate(F, T, p.beta, K, v); double e = 0; for (size_t i = 0; i < K.size(); i++) e = std::max(e, std::fabs(sabr_vol(F, K[i], T, out) - v[i])); return e; }
int main() {
    SabrParams a{.04, .5, -.3, .5};
    sec("hagan_lognormal_beta_half", [&] { return near(sabr_vol(.03, .02, 2, a), .3098088585493147, 1e-11) && near(sabr_vol(.03, .05, 2, a), .2197854564401762, 1e-11); });
    sec("hagan_beta_one", [&] { SabrParams b{.25, 1, -.4, .6}; return near(sabr_vol(100, 80, 1, b), .2856697315517138, 1e-11) && near(sabr_vol(100, 130, 1, b), .23618898862197296, 1e-11); });
    sec("hagan_beta_zero", [&] { SabrParams b{.007, 0, .2, .3}; return near(sabr_vol(.05, .04, 5, b), .16048302085579874, 1e-11) && near(sabr_vol(.05, .08, 5, b), .14580347045359252, 1e-11); });
    sec("atm_exact", [&] { return near(sabr_vol(.03, .03, 2, a), .23752017417630725, 1e-12); });
    sec("atm_continuity", [&] { double atm = sabr_vol(.03, .03, 2, a); for (double e : {1e-16, 1e-14, 1e-12, 1e-10, 1e-8, 1e-6}) for (double s : {1., -1.}) { double v = sabr_vol(.03, .03 * (1 + s * e), 2, a); if (!std::isfinite(v) || std::fabs(v - atm) > 1e-5 * (e > 1e-7 ? 1 : .01) + 1e-7) { fprintf(stderr, "e %g v %.12g atm %.12g\n", e, v, atm); return false; } } return true; });
    sec("no_vol_of_vol_limit", [&] { SabrParams z{.04, .5, .3, 1e-6}; SabrParams zero{.04, .5, .3, 0}; double w = sabr_vol(.03, .025, 1, z); return near(w, .24177338101067186, 1e-9) && std::isfinite(sabr_vol(.03, .025, 1, zero)) && near(sabr_vol(.03, .025, 1, zero), w, 1e-6); });
    sec("calibrate_exact_recovery", [&] { SabrParams o; smile(.03, 2, a, {.015, .02, .025, .03, .035, .04, .05}, 0, o); return near(o.alpha, .04, 2e-4) && near(o.rho, -.3, 2e-3) && near(o.nu, .5, 2e-3) && near(o.beta, .5, 0); });
    sec("calibrate_negative_skew", [&] { SabrParams p{.3, 1, -.75, .9}, o; double e = smile(100, .5, p, {70, 80, 90, 95, 100, 105, 110, 120, 130}, 0, o); return e < 1e-5 && near(o.rho, -.75, 5e-3) && near(o.nu, .9, 5e-3); });
    sec("calibrate_noisy_stays_in_bounds", [&] { for (unsigned s = 1; s <= 30; s++) { SabrParams o; double e = smile(.03, 2, a, {.015, .02, .025, .03, .035, .04, .05}, .004, o, s); if (!(std::fabs(o.rho) < 1 && o.alpha > 0 && o.nu >= 0) || e > .02) { fprintf(stderr, "s %u e %g rho %g\n", s, e, o.rho); return false; } } return true; });
    sec("calibrate_rejects_bad_input", [&] { auto isbad = [](auto f) { try { f(); } catch (const std::invalid_argument&) { return true; } return false; }; return isbad([] { sabr_calibrate(.03, 1, .5, {.03, .04}, {.2, .2}); }) && isbad([] { sabr_calibrate(.03, 1, .5, {.03, .04, .05}, {.2, .2}); }) && isbad([] { sabr_calibrate(-.03, 1, .5, {.03, .04, .05}, {.2, .2, .2}); }) && isbad([] { sabr_calibrate(.03, 1, .5, {0, .04, .05}, {.2, .2, .2}); }) && isbad([] { sabr_calibrate(.03, 0, .5, {.03, .04, .05}, {.2, .2, .2}); }); });
    sec("smile_shape", [&] { return sabr_vol(.03, .02, 2, a) > sabr_vol(.03, .03, 2, a) && sabr_vol(.03, .1, 2, a) > sabr_vol(.03, .05, 2, a) * .95; });
    return 0;
}
