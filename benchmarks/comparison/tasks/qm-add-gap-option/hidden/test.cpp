#include "quantModeling/models/equity/black_scholes.hpp"
#include "quantModeling/pricers/context.hpp"
#include "quantModeling/engines/analytic/black_scholes.hpp"
#include "quantModeling/engines/analytic/gap.hpp"
#include "quantModeling/instruments/equity/gap.hpp"
#include "quantModeling/instruments/equity/digital.hpp"
#include "quantModeling/pricers/adapters/equity_gap.hpp"
#include "quantModeling/pricers/registry.hpp"
#include "chk.hpp"
using namespace quantModeling;
static double N(double x) { return .5 * erfc(-x * M_SQRT1_2); }
static double gap(double S, double K, double H, double r, double q, double v, double T, bool c) { double d1 = (log(S / H) + (r - q + .5 * v * v) * T) / (v * sqrt(T)), d2 = d1 - v * sqrt(T); return c ? S * exp(-q * T) * N(d1) - K * exp(-r * T) * N(d2) : K * exp(-r * T) * N(-d2) - S * exp(-q * T) * N(-d1); }
static PricingResult px(double K, double H, bool c, double S = 100) { GapBSInput in{}; in.spot = S; in.strike = K; in.trigger = H; in.maturity = 1.25; in.rate = .04; in.dividend = .015; in.vol = .3; in.is_call = c; PricingRequest r{InstrumentKind::EquityGapOption, ModelKind::BlackScholes, EngineKind::Analytic, PricingInput{in}}; return default_registry().price(r); }
int main() {
    sec("registry_call", [] { return near(px(100, 110, true).npv, gap(100, 100, 110, .04, .015, .3, 1.25, true), 1e-10) && near(px(120, 95, true).npv, gap(100, 120, 95, .04, .015, .3, 1.25, true), 1e-10); });
    sec("registry_put", [] { return near(px(100, 90, false).npv, gap(100, 100, 90, .04, .015, .3, 1.25, false), 1e-10) && near(px(80, 110, false).npv, gap(100, 80, 110, .04, .015, .3, 1.25, false), 1e-10); });
    sec("trigger_equals_strike_is_vanilla", [] { VanillaBSInput v{}; v.spot = 100; v.strike = 105; v.maturity = 1.25; v.rate = .04; v.dividend = .015; v.vol = .3; v.is_call = true; PricingRequest r{InstrumentKind::EquityVanillaOption, ModelKind::BlackScholes, EngineKind::Analytic, PricingInput{v}}; return near(px(105, 105, true).npv, default_registry().price(r).npv, 1e-10); });
    sec("delta_populated", [] { auto p = px(100, 110, true); double h = 1e-3, fd = (px(100, 110, true, 100 + h).npv - px(100, 110, true, 100 - h).npv) / (2 * h); return p.greeks.delta.has_value() && near(*p.greeks.delta, fd, 1e-5); });
    sec("digital_decomposition", [] { double a = px(100, 110, true).npv, b = px(90, 110, true).npv; return near(b - a, 10 * exp(-.04 * 1.25) * N((log(100. / 110) + (.04 - .015 - .045) * 1.25) / (.3 * sqrt(1.25))), 1e-9); });
    sec("other_engines_refuse", [] { auto p = std::make_shared<PlainVanillaPayoff>(OptionType::Call, Real(100)); auto e = std::make_shared<EuropeanExercise>(Real(1)); GapOption g(p, e, 110); auto m = std::make_shared<BlackScholesModel>(Real(100), Real(.03), Real(0), Real(.2)); PricingSettings s; MarketView mv{}; PricingContext c{mv, s, m}; BSEuroVanillaAnalyticEngine en(c); try { g.accept(en); } catch (const UnsupportedInstrument&) { return near(g.trigger, 110, 0) && near(g.notional, 1, 0); } return false; });
    return 0;
}
