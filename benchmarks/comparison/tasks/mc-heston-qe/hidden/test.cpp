#include "heston.hpp"
#include "chk.hpp"
using namespace mc;
// Andersen (2008) test cases; QuantLib's analytic engine and an independent Gil-Pelaez agree to 1e-13.
static HestonParams C1{100, 0, 0, .04, .5, .04, 1.0, -.9}, C2{100, 0, 0, .04, .3, .04, .9, -.5}, C3{100, 0, 0, .09, 1, .09, 1.0, -.3}, OK{100, .02, .01, .04, 1.5, .04, .5, -.7};
static bool within(const HestonParams& p, double K, double T, int st, double want, double tol, unsigned seed) { auto r = heston_call_mc(p, K, T, st, 1000000, seed); fprintf(stderr, "bias %.4f se %.4f\n", r.price - want, r.std_error); return std::isfinite(r.price) && std::fabs(r.price - want) < tol + 3.5 * r.std_error; }
int main() {
    sec("andersen_case1_atm", [] { return within(C1, 100, 10, 80, 13.084670136992312, .12, 1); }, 200);
    sec("andersen_case1_itm", [] { return within(C1, 70, 10, 80, 35.84976970383796, .12, 2); }, 200);
    sec("andersen_case1_otm", [] { return within(C1, 140, 10, 80, .2957744357980179, .06, 3); }, 200);
    sec("andersen_case2", [] { return within(C2, 100, 15, 120, 16.64922292035864, .12, 4); }, 200);
    sec("andersen_case3", [] { return within(C3, 100, 5, 40, 21.795287742473523, .12, 5); }, 200);
    sec("martingale", [] { auto r = heston_forward_mc(C1, 10, 80, 1000000, 6); fprintf(stderr, "bias %.4f se %.4f\n", r.price - 100, r.std_error); return std::fabs(r.price - 100) < 3.5 * r.std_error + .02; }, 200);
    sec("martingale_extreme", [] { HestonParams p{100, 0, 0, .04, .1, .04, 2.0, -.9}; auto r = heston_forward_mc(p, 5, 20, 1000000, 7); fprintf(stderr, "bias %.4f se %.4f\n", r.price - 100, r.std_error); return std::isfinite(r.price) && std::fabs(r.price - 100) < 3.5 * r.std_error + .05; }, 200);
    sec("feller_ok_regime", [] { return within(OK, 100, 1, 8, 7.526116651503193, .05, 8); }, 200);
    sec("reproducible", [] { auto a = heston_call_mc(C1, 100, 1, 8, 10000, 9), b = heston_call_mc(C1, 100, 1, 8, 10000, 9), c = heston_call_mc(C1, 100, 1, 8, 10000, 10); return a.price == b.price && a.price != c.price; });
    return 0;
}
