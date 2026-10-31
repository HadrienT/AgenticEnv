#pragma once
#include <cstddef>
#include <memory>
#include <string>
#include <vector>
namespace inst {
struct Market { double spot, rate, vol; };
class EuropeanOption; class DigitalOption; class BarrierOption; class ZeroCouponBond; class Portfolio;
class Visitor { public: virtual ~Visitor() = default; virtual void visit(const EuropeanOption&) = 0; virtual void visit(const DigitalOption&) = 0; virtual void visit(const BarrierOption&) = 0; virtual void visit(const ZeroCouponBond&) = 0; virtual void visit(const Portfolio&) = 0; };
class Instrument { public: virtual ~Instrument() = default; virtual void accept(Visitor&) const = 0; virtual std::unique_ptr<Instrument> clone() const = 0; };
template <class D> struct Impl : Instrument { void accept(Visitor& v) const override { v.visit(static_cast<const D&>(*this)); } std::unique_ptr<Instrument> clone() const override { return std::make_unique<D>(static_cast<const D&>(*this)); } };
class EuropeanOption : public Impl<EuropeanOption> { double k_, t_; bool c_; public: EuropeanOption(double k, double t, bool c) : k_(k), t_(t), c_(c) {} double strike() const { return k_; } double maturity() const { return t_; } bool is_call() const { return c_; } };
class DigitalOption : public Impl<DigitalOption> { double k_, t_, c_; public: DigitalOption(double k, double t, double c) : k_(k), t_(t), c_(c) {} double strike() const { return k_; } double maturity() const { return t_; } double cash() const { return c_; } };
class BarrierOption : public Impl<BarrierOption> { double k_, h_, t_; public: BarrierOption(double k, double h, double t) : k_(k), h_(h), t_(t) {} double strike() const { return k_; } double barrier() const { return h_; } double maturity() const { return t_; } };
class ZeroCouponBond : public Impl<ZeroCouponBond> { double t_, n_; public: ZeroCouponBond(double t, double n) : t_(t), n_(n) {} double maturity() const { return t_; } double notional() const { return n_; } };
struct Position { std::unique_ptr<Instrument> item; double quantity; };
class Portfolio : public Instrument { std::vector<Position> p_; public: Portfolio() = default; void add(std::unique_ptr<Instrument> i, double q) { p_.push_back({std::move(i), q}); } std::size_t size() const { return p_.size(); } const std::vector<Position>& positions() const { return p_; } void accept(Visitor& v) const override { v.visit(*this); } std::unique_ptr<Instrument> clone() const override { auto c = std::make_unique<Portfolio>(); for (auto& x : p_) c->add(x.item->clone(), x.quantity); return c; } };
class PricingVisitor : public Visitor { protected: Market m_; double r_ = 0; public: explicit PricingVisitor(Market m) : m_(m) {} double result() const { return r_; } void visit(const EuropeanOption&) override; void visit(const DigitalOption&) override; void visit(const BarrierOption&) override; void visit(const ZeroCouponBond&) override; void visit(const Portfolio&) override; };
class DeltaVisitor : public Visitor { Market m_; double r_ = 0; template <class I> void bump(const I&); public: explicit DeltaVisitor(Market m) : m_(m) {} double result() const { return r_; } void visit(const EuropeanOption&) override; void visit(const DigitalOption&) override; void visit(const BarrierOption&) override; void visit(const ZeroCouponBond&) override; void visit(const Portfolio&) override; };
class JsonVisitor : public Visitor { std::string r_; public: std::string result() const { return r_; } void visit(const EuropeanOption&) override; void visit(const DigitalOption&) override; void visit(const BarrierOption&) override; void visit(const ZeroCouponBond&) override; void visit(const Portfolio&) override; };
}
