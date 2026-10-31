#include "engine.hpp"
#include "chk.hpp"
#include <vector>
using namespace mc;
static double N(double x) { return .5 * erfc(-x * M_SQRT1_2); }
static double bs(double S, double K, double r, double q, double v, double T, bool c) { double d1 = (log(S / K) + (r - q + .5 * v * v) * T) / (v * sqrt(T)), d2 = d1 - v * sqrt(T); return c ? S * exp(-q * T) * N(d1) - K * exp(-r * T) * N(d2) : K * exp(-r * T) * N(-d2) - S * exp(-q * T) * N(-d1); }
static double dob(double S, double K, double H, double r, double q, double v, double T) { double l = (r - q + .5 * v * v) / (v * v), y = log(H * H / (S * K)) / (v * sqrt(T)) + l * v * sqrt(T); return bs(S, K, r, q, v, T, true) - S * exp(-q * T) * pow(H / S, 2 * l) * N(y) + K * exp(-r * T) * pow(H / S, 2 * l - 2) * N(y - v * sqrt(T)); }
int main() {
    Market m{100, .05, 0, .2}, mq{100, .05, .03, .25};
    sec("european_drift", [&] { auto r = european(m, 105, 1, true, 4000000, 1, false); return near(r.price, bs(100, 105, .05, 0, .2, 1, true), 4 * r.std_error); });
    sec("european_q_discount", [&] { auto r = european(mq, 95, 2, true, 4000000, 2, false); auto s = european(mq, 95, 2, false, 4000000, 3, false); return near(r.price, bs(100, 95, .05, .03, .25, 2, true), 4 * r.std_error) && near(s.price, bs(100, 95, .05, .03, .25, 2, false), 4 * s.std_error); });
    sec("antithetic_se", [&] { std::vector<double> x; double se = 0; for (int s = 0; s < 40; s++) { auto r = european(m, 100, 1, true, 20000, 10 + s, true); x.push_back(r.price); se += r.std_error / 40; } double a = 0, v = 0; for (double p : x) a += p / 40; for (double p : x) v += (p - a) * (p - a) / 39; double k = std::sqrt(v) / se; fprintf(stderr, "ratio %.2f\n", k); return k > .7 && k < 1.35; });
    sec("asian_average_dates", [&] { auto r = asian(Market{100, .05, 0, .2}, 100, 1, 12, 2000000, 4); return near(r.price, 6.15604580887108, 4 * r.std_error + 2e-4); });
    sec("barrier_bridge", [&] { auto r = down_out_call(m, 100, 90, 1, 10, 3000000, 5); double w = dob(100, 100, 90, .05, 0, .2, 1); return near(r.price, w, 4 * r.std_error + .004); });
    sec("threads_independent", [&] { auto a = digital_mt(m, 100, 1, 8000000, 6, 8); auto b = digital_mt(m, 100, 1, 800000, 7, 1); double ratio = a.std_error / b.std_error; std::vector<double> x; for (int s = 0; s < 30; s++) x.push_back(digital_mt(m, 100, 1, 80000, 100 + s, 8).price); double av = 0, v = 0; for (double p : x) av += p / 30; for (double p : x) v += (p - av) * (p - av) / 29; auto c = digital_mt(m, 100, 1, 80000, 500, 8); double k = std::sqrt(v) / c.std_error; fprintf(stderr, "ratio %.2f\n", k); return k < 1.6 && k > .6 && ratio < 1; });
    sec("threads_same_price", [&] { auto a = digital_mt(m, 100, 1, 8000000, 8, 8); double w = exp(-.05) * N((.05 - .02) / .2); return near(a.price, w, 4 * a.std_error) && digital_mt(m, 100, 1, 1000, 9, 7).std_error > 0 && near(double(1), 1, 0); });
    sec("digital_at_strike", [&] { auto a = digital_mt(m, 100, 1, 1003, 8, 7); return a.price > 0; });
    sec("regression_european_put", [&] { auto r = european(m, 100, 1, false, 2000000, 12, true); return near(r.price, bs(100, 100, .05, 0, .2, 1, false), 4 * r.std_error + .01); });
    return 0;
}
