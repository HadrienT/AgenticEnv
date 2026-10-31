#include "quantModeling/instruments/base.hpp"
#include "quantModeling/pricers/registry.hpp"
#include "chk.hpp"
using namespace quantModeling;
static double N(double x) { return .5 * erfc(-x * M_SQRT1_2); }
static double bsc(double S, double K, double r, double q, double v, double T, bool c) { double d1 = (log(S / K) + (r - q + .5 * v * v) * T) / (v * sqrt(T)), d2 = d1 - v * sqrt(T); return c ? S * exp(-q * T) * N(d1) - K * exp(-r * T) * N(d2) : K * exp(-r * T) * N(-d2) - S * exp(-q * T) * N(-d1); }
static PricingResult px(bool call, BarrierType t, double H) { BarrierBSInput in{}; in.spot = 100; in.strike = 100; in.maturity = 1; in.rate = .05; in.dividend = .02; in.vol = .2; in.is_call = call; in.barrier_type = t; in.barrier_level = H; in.n_steps = 26; in.brownian_bridge = true; in.n_paths = 400000; in.seed = 11; PricingRequest r{InstrumentKind::EquityBarrierOption, ModelKind::BlackScholes, EngineKind::MonteCarlo, PricingInput{in}}; return default_registry().price(r); }
int main() {
    double S = 100, K = 100, r = .05, q = .02, v = .2, T = 1, l = (r - q + .5 * v * v) / (v * v);
    sec("down_out_call_matches_closed_form", [&] { double H = 90, y = log(H * H / (S * K)) / (v * sqrt(T)) + l * v * sqrt(T); double w = bsc(S, K, r, q, v, T, true) - S * exp(-q * T) * pow(H / S, 2 * l) * N(y) + K * exp(-r * T) * pow(H / S, 2 * l - 2) * N(y - v * sqrt(T)); auto p = px(true, BarrierType::DownAndOut, H); fprintf(stderr, "got %.4f want %.4f se %.4f\n", p.npv, w, p.mc_std_error); return fabs(p.npv - w) < 4 * p.mc_std_error + .02; }, 200);
    sec("up_out_put_matches_closed_form", [&] { double H = 115, y = log(H * H / (S * K)) / (v * sqrt(T)) + l * v * sqrt(T); double w = bsc(S, K, r, q, v, T, false) - (-S * exp(-q * T) * pow(H / S, 2 * l) * N(-y) + K * exp(-r * T) * pow(H / S, 2 * l - 2) * N(-y + v * sqrt(T))); auto p = px(false, BarrierType::UpAndOut, H); fprintf(stderr, "got %.4f want %.4f se %.4f\n", p.npv, w, p.mc_std_error); return fabs(p.npv - w) < 4 * p.mc_std_error + .02; }, 200);
    return 0;
}
