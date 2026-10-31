#include "instruments.hpp"
#include "chk.hpp"
#include <map>
#include <memory>
#include <string>
#include <type_traits>
using namespace inst;
static double N(double x) { return .5 * erfc(-x * M_SQRT1_2); }
static double bs(double S, double K, double r, double v, double T) { double d1 = (log(S / K) + (r + .5 * v * v) * T) / (v * sqrt(T)); return S * N(d1) - K * exp(-r * T) * N(d1 - v * sqrt(T)); }
template <class V, class I> static double run(V v, const I& i) { i.accept(v); return v.result(); }
struct Partial : Visitor { void visit(const EuropeanOption&) override {} };
struct Counter : Visitor { std::map<std::string, int> c; void visit(const EuropeanOption&) override { c["e"]++; } void visit(const DigitalOption&) override { c["d"]++; } void visit(const BarrierOption&) override { c["b"]++; } void visit(const ZeroCouponBond&) override { c["z"]++; }
    void visit(const Portfolio& p) override { c["p"]++; for (const auto& x : p.positions()) x.item->accept(*this); } };
static std::unique_ptr<Portfolio> nest() { auto in = std::make_unique<Portfolio>(); in->add(std::make_unique<EuropeanOption>(100, 1, true), 3); in->add(std::make_unique<ZeroCouponBond>(2, 1000), -1);
    auto out = std::make_unique<Portfolio>(); out->add(std::move(in), 2); out->add(std::make_unique<DigitalOption>(95, .5, 10), .5); return out; }
int main() {
    Market m{100, .03, .25};
    sec("pricing_european", [&] { double c = bs(100, 105, .03, .25, 1.5); return near(run(PricingVisitor(m), EuropeanOption(105, 1.5, true)), c, 1e-10) && near(run(PricingVisitor(m), EuropeanOption(105, 1.5, false)), c - 100 + 105 * exp(-.045), 1e-10); });
    sec("pricing_digital", [&] { double d2 = (log(100 / 95.) + (.03 - .03125) * 1) / .25; return near(run(PricingVisitor(m), DigitalOption(95, 1, 7)), 7 * exp(-.03) * N(d2), 1e-10); });
    sec("pricing_barrier", [&] { double S = 100, K = 105, H = 85, r = .03, v = .25, T = 1, l = (r + .5 * v * v) / (v * v);
        double want = bs(S, K, r, v, T) - pow(H / S, 2 * l) * S * N((log(H * H / (S * K)) + (r + .5 * v * v) * T) / (v * sqrt(T))) + pow(H / S, 2 * l - 2) * K * exp(-r * T) * N((log(H * H / (S * K)) + (r + .5 * v * v) * T) / (v * sqrt(T)) - v * sqrt(T));
        return near(run(PricingVisitor(m), BarrierOption(105, 85, 1)), want, 1e-9) && run(PricingVisitor(Market{100, .03, .25}), BarrierOption(100, 99.9999, 1)) < .01; });
    sec("pricing_zcb", [&] { return near(run(PricingVisitor(m), ZeroCouponBond(2, 1000)), 1000 * exp(-.06), 1e-10); });
    sec("delta", [&] { auto bump = [&](const Instrument& i) { double h = 1e-4; PricingVisitor u(Market{100 + h, .03, .25}), d(Market{100 - h, .03, .25}); i.accept(u); i.accept(d); return (u.result() - d.result()) / (2 * h); };
        EuropeanOption e(105, 1.5, true); DigitalOption g(95, 1, 7); BarrierOption b(105, 85, 1); ZeroCouponBond z(2, 1000); auto p = nest();
        return near(run(DeltaVisitor(m), e), bump(e), 1e-5) && near(run(DeltaVisitor(m), g), bump(g), 1e-5) && near(run(DeltaVisitor(m), b), bump(b), 1e-5) && near(run(DeltaVisitor(m), z), 0, 1e-10) && near(run(DeltaVisitor(m), *p), bump(*p), 1e-5); });
    sec("portfolio_nested", [&] { auto p = nest(); double d2 = (log(100 / 95.) + (.03 - .03125) * .5) / (.25 * sqrt(.5)); double want = 2 * (3 * bs(100, 100, .03, .25, 1) - 1000 * exp(-.06)) + .5 * 10 * exp(-.015) * N(d2); return near(run(PricingVisitor(m), *p), want, 1e-9) && p->size() == 2; });
    sec("json_exact", [&] { auto j = [](const Instrument& i) { JsonVisitor v; i.accept(v); return v.result(); }; Portfolio p; p.add(std::make_unique<EuropeanOption>(100, 1.5, true), 2); auto q = std::make_unique<Portfolio>(); q->add(std::make_unique<ZeroCouponBond>(2, 1000), .25); p.add(std::move(q), 1);
        auto a = j(EuropeanOption(100, 1.5, true)) == R"({"type":"european","strike":100,"maturity":1.5,"call":true})" && j(DigitalOption(100, 1, 10)) == R"({"type":"digital","strike":100,"maturity":1,"cash":10})" && j(BarrierOption(100, 80, 1)) == R"({"type":"barrier","strike":100,"barrier":80,"maturity":1})" && j(ZeroCouponBond(2, 1000)) == R"({"type":"zcb","maturity":2,"notional":1000})";
        std::string got = j(p), want = R"({"type":"portfolio","positions":[{"quantity":2,"item":{"type":"european","strike":100,"maturity":1.5,"call":true}},{"quantity":1,"item":{"type":"portfolio","positions":[{"quantity":0.25,"item":{"type":"zcb","maturity":2,"notional":1000}}]}}]})";
        if (got != want) fprintf(stderr, "%s\n", got.c_str()); return a && got == want; });
    sec("user_visitor", [&] { auto p = nest(); Counter c; p->accept(c); return c.c["p"] == 2 && c.c["e"] == 1 && c.c["z"] == 1 && c.c["d"] == 1 && c.c["b"] == 0; });
    sec("adding_overload_is_compile_error", [&] { return std::is_abstract_v<Partial> && std::is_abstract_v<Visitor> && !std::is_abstract_v<Counter> && std::is_abstract_v<Instrument> && std::has_virtual_destructor_v<Instrument>; });
    sec("visitor_reusable", [&] { PricingVisitor v(m); auto p = nest(); p->accept(v); double a = v.result(); p->accept(v); ZeroCouponBond z(1, 1); z.accept(v); double b = v.result(); p->accept(v); JsonVisitor j; z.accept(j); auto s1 = j.result(); z.accept(j); return near(v.result(), a, 1e-12) && near(b, exp(-.03), 1e-12) && s1 == j.result(); });
    sec("clone_is_deep", [&] { auto p = nest(); auto c = p->clone(); double a = run(PricingVisitor(m), *c); p->add(std::make_unique<ZeroCouponBond>(1, 5000), 1); auto* q = const_cast<Portfolio*>(static_cast<const Portfolio*>(c.get())); return near(run(PricingVisitor(m), *c), a, 1e-12) && q->size() == 2 && run(PricingVisitor(m), *p) > a + 100; });
    return 0;
}
