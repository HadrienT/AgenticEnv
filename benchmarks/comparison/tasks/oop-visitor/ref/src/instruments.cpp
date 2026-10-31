#include "instruments.hpp"
#include <cmath>
namespace inst {
static double N(double x) { return .5 * std::erfc(-x * M_SQRT1_2); }
static double call(double S, double K, double r, double v, double T) { double d1 = (std::log(S / K) + (r + .5 * v * v) * T) / (v * std::sqrt(T)); return S * N(d1) - K * std::exp(-r * T) * N(d1 - v * std::sqrt(T)); }
void PricingVisitor::visit(const EuropeanOption& o) { double c = call(m_.spot, o.strike(), m_.rate, m_.vol, o.maturity()); r_ = o.is_call() ? c : c - m_.spot + o.strike() * std::exp(-m_.rate * o.maturity()); }
void PricingVisitor::visit(const DigitalOption& o) { double T = o.maturity(), d2 = (std::log(m_.spot / o.strike()) + (m_.rate - .5 * m_.vol * m_.vol) * T) / (m_.vol * std::sqrt(T)); r_ = o.cash() * std::exp(-m_.rate * T) * N(d2); }
void PricingVisitor::visit(const BarrierOption& o) { double S = m_.spot, K = o.strike(), H = o.barrier(), r = m_.rate, v = m_.vol, T = o.maturity(), l = (r + .5 * v * v) / (v * v), y = (std::log(H * H / (S * K)) + (r + .5 * v * v) * T) / (v * std::sqrt(T)); r_ = call(S, K, r, v, T) - std::pow(H / S, 2 * l) * S * N(y) + std::pow(H / S, 2 * l - 2) * K * std::exp(-r * T) * N(y - v * std::sqrt(T)); }
void PricingVisitor::visit(const ZeroCouponBond& o) { r_ = o.notional() * std::exp(-m_.rate * o.maturity()); }
void PricingVisitor::visit(const Portfolio& p) { double t = 0; for (auto& x : p.positions()) { x.item->accept(*this); t += x.quantity * r_; } r_ = t; }
template <class I> void DeltaVisitor::bump(const I& i) { double h = 1e-4; Market u = m_, d = m_; u.spot += h; d.spot -= h; PricingVisitor a(u), b(d); i.accept(a); i.accept(b); r_ = (a.result() - b.result()) / (2 * h); }
void DeltaVisitor::visit(const EuropeanOption& o) { bump(o); }
void DeltaVisitor::visit(const DigitalOption& o) { bump(o); }
void DeltaVisitor::visit(const BarrierOption& o) { bump(o); }
void DeltaVisitor::visit(const ZeroCouponBond&) { r_ = 0; }
void DeltaVisitor::visit(const Portfolio& p) { double t = 0; for (auto& x : p.positions()) { x.item->accept(*this); t += x.quantity * r_; } r_ = t; }
static std::string num(double x) { std::string s = std::to_string(x); s.erase(s.find_last_not_of('0') + 1); if (s.back() == '.') s.pop_back(); return s; }
void JsonVisitor::visit(const EuropeanOption& o) { r_ = "{\"type\":\"european\",\"strike\":" + num(o.strike()) + ",\"maturity\":" + num(o.maturity()) + ",\"call\":" + (o.is_call() ? "true" : "false") + "}"; }
void JsonVisitor::visit(const DigitalOption& o) { r_ = "{\"type\":\"digital\",\"strike\":" + num(o.strike()) + ",\"maturity\":" + num(o.maturity()) + ",\"cash\":" + num(o.cash()) + "}"; }
void JsonVisitor::visit(const BarrierOption& o) { r_ = "{\"type\":\"barrier\",\"strike\":" + num(o.strike()) + ",\"barrier\":" + num(o.barrier()) + ",\"maturity\":" + num(o.maturity()) + "}"; }
void JsonVisitor::visit(const ZeroCouponBond& o) { r_ = "{\"type\":\"zcb\",\"maturity\":" + num(o.maturity()) + ",\"notional\":" + num(o.notional()) + "}"; }
void JsonVisitor::visit(const Portfolio& p) { std::string s = "{\"type\":\"portfolio\",\"positions\":["; bool f = true; for (auto& x : p.positions()) { x.item->accept(*this); if (!f) s += ","; f = false; s += "{\"quantity\":" + num(x.quantity) + ",\"item\":" + r_ + "}"; } r_ = s + "]}"; }
}
