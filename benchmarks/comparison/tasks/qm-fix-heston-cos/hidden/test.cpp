#include "quantModeling/engines/analytic/heston_cos.hpp"
#include "chk.hpp"
using namespace quantModeling;
int main() {
    // Bachelier-free truth: QuantLib and Gil-Pelaez agree to 1e-13.
    sec("andersen_case_price", [] { HestonParams p{.04, .5, .04, 1.0, -.9}; HestonCOSSettings s; s.truncation_L = 12; return near(heston_cos_price(100, 100, 10, 1, p, true), 13.084670136992312, 2e-3); });
    sec("standard_case_price", [] { HestonParams p{.04, 1.5, .04, .5, -.7}; double F = 100 * exp(.01); return near(heston_cos_price(F, 100, 1, exp(-.02), p, true), 7.526116651503193, 1e-4); });
    return 0;
}
