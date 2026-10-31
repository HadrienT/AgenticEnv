#include <vector>
#include <algorithm>
#include "iv.hpp"
#include "chk.hpp"
#include <chrono>
#include <limits>
#include <random>
using namespace model;
static double intr(double S, double K, double r, double q, double T, bool c) { double f = S * exp(-q * T) - K * exp(-r * T); return c ? std::max(f, 0.) : std::max(-f, 0.); }
static bool grid(double width, double tvmin, double tvmax, bool call, double tol) { std::mt19937_64 g(77); std::uniform_real_distribution<double> u(0, 1); double S = 100; long used = 0; double worst = 0; for (int i = 0; i < 400000; i++) { double sg = exp(log(.01) + u(g) * (log(5.) - log(.01))), T = exp(log(1 / 365.) + u(g) * (log(30.) - log(1 / 365.))), m = (2 * u(g) - 1) * width * sg * sqrt(T), r = .03 * u(g), q = .02 * u(g), K = S * exp((r - q) * T - m); double p = bs_price(S, K, r, q, sg, T, call), tv = p - intr(S, K, r, q, T, call); if (tv < tvmin * S || tv > tvmax * S) continue; double up = call ? S * exp(-q * T) : K * exp(-r * T); if (up - p < 1e-5 * up || tv < 1e-5 * p) continue; used++; double v = implied_vol(p, S, K, r, q, T, call), e = fabs(v - sg) / sg; if (!(e <= tol)) { worst = 1; fprintf(stderr, "got v=%.10g sg=%.10g T=%.5g m=%.4g p=%.5g tv=%.3g\n", v, sg, T, m, p, tv); return false; } } fprintf(stderr, "used %ld\n", used); return used > 500; }
int main() {
    sec("roundtrip_core_grid", [] { return grid(1.5, 1e-4, 1e9, true, 1e-7); }, 120);
    sec("roundtrip_wings", [] { return grid(4, 1e-7, 1e9, true, 1e-6); }, 120);
    sec("roundtrip_tiny_time_value", [] { return grid(8, 1e-10, 1e-7, true, 1e-3); }, 120);
    sec("put_side", [] { return grid(4, 1e-7, 1e9, false, 1e-6); }, 120);
    sec("time_value_zero", [] { double i = intr(100, 80, 0, 0, 1, true); return std::isnan(implied_vol(i, 100, 80, 0, 0, 1, true)); });
    sec("below_intrinsic_is_nan", [] { return std::isnan(implied_vol(10, 100, 80, 0, 0, 1, true)) && std::isnan(implied_vol(.5, 100, 110, .05, 0, 1, false)) && std::isnan(implied_vol(0, 100, 150, 0, 0, 1, true)); });
    sec("above_upper_bound_is_nan", [] { return std::isnan(implied_vol(101, 100, 80, 0, 0, 1, true)) && std::isnan(implied_vol(100, 100, 100, 0, 0, 1, true)) && std::isnan(implied_vol(99, 100, 90, .0, 0, 1, false)); });
    sec("no_exceptions_on_garbage", [] { double inf = std::numeric_limits<double>::infinity(), nan = std::numeric_limits<double>::quiet_NaN(); return std::isnan(implied_vol(nan, 100, 100, 0, 0, 1, true)) && std::isnan(implied_vol(5, -1, 100, 0, 0, 1, true)) && std::isnan(implied_vol(5, 100, 0, 0, 0, 1, true)) && std::isnan(implied_vol(5, 100, 100, 0, 0, 0, true)) && std::isnan(implied_vol(inf, 100, 100, 0, 0, 1, true)) && std::isnan(implied_vol(5, 100, 100, 0, 0, inf, true)); });
    sec("speed", [] { std::mt19937_64 g(1); std::uniform_real_distribution<double> u(0, 1); std::vector<double> P, K, T, Sg; int n = 1000000; for (int i = 0; i < n; i++) { double sg = .05 + u(g), t = .05 + 3 * u(g), k = 100 * exp((2 * u(g) - 1) * 1.5 * sg * sqrt(t)); P.push_back(bs_price(100, k, .02, 0, sg, t, true)); K.push_back(k); T.push_back(t); } auto t0 = std::chrono::steady_clock::now(); volatile double s = 0; for (int i = 0; i < n; i++) s = s + implied_vol(P[i], 100, K[i], .02, 0, T[i], true); double d = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count(); fprintf(stderr, "%.2fs\n", d); return d < 2; }, 60);
    return 0;
}
