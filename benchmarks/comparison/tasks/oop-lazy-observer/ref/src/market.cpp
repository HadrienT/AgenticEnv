#include "market.hpp"
#include <stdexcept>
namespace mkt {
struct Link { Observer* o; };
Observer::~Observer() { if (link_) { link_->o = nullptr; for (auto& s : subjects_) s->remove_(link_.get()); } }
void Observer::observe(const std::shared_ptr<Observable>& o) { if (!link_) link_ = std::make_shared<Link>(Link{this}); if (std::find(subjects_.begin(), subjects_.end(), o) != subjects_.end()) return; subjects_.push_back(o); o->add_(link_); }
void Observer::stop_observing(const std::shared_ptr<Observable>& o) { auto it = std::find(subjects_.begin(), subjects_.end(), o); if (it == subjects_.end()) return; o->remove_(link_.get()); subjects_.erase(it); }
Observable::~Observable() {}
void Observable::add_(std::shared_ptr<Link> l) { links_.push_back(std::move(l)); }
void Observable::remove_(Link* l) { links_.erase(std::remove_if(links_.begin(), links_.end(), [&](auto& p) { return p.get() == l; }), links_.end()); }
void Observable::notify() { auto copy = links_; for (auto& l : copy) if (l->o) l->o->update(); }
Quote::Quote(double v) : v_(v) {}
double Quote::value() const { return v_; }
void Quote::set(double v) { if (v == v_) return; v_ = v; notify(); }
double LazyObject::value() const { if (dirty_) { v_ = compute(); n_++; dirty_ = false; sent_ = false; } return v_; }
long LazyObject::computations() const { return n_; }
void LazyObject::update() { dirty_ = true; if (!sent_) { sent_ = true; notify(); } }
struct Intrinsic : Engine { double price(double s, double k, double v) const override { return std::max(s - k, 0.0) + v; } std::string name() const override { return "intrinsic"; } };
struct Flat : Engine { double price(double, double k, double) const override { return k; } std::string name() const override { return "flat"; } };
EngineFactory& EngineFactory::instance() { static EngineFactory f = [] { EngineFactory g; g.add("intrinsic", [] { return std::make_unique<Intrinsic>(); }); g.add("flat", [] { return std::make_unique<Flat>(); }); return g; }(); return f; }
void EngineFactory::add(const std::string& k, std::function<std::unique_ptr<Engine>()> m) { m_[k] = std::move(m); }
std::unique_ptr<Engine> EngineFactory::create(const std::string& k) const { auto i = m_.find(k); if (i == m_.end()) throw std::invalid_argument(k); return i->second(); }
std::vector<std::string> EngineFactory::keys() const { std::vector<std::string> r; for (auto& [k, v] : m_) r.push_back(k); return r; }
MemoEngine::MemoEngine(std::unique_ptr<Engine> i) : in_(std::move(i)) {}
double MemoEngine::price(double a, double b, double c) const { auto k = std::make_tuple(a, b, c); auto i = c_.find(k); if (i != c_.end()) return i->second; return c_[k] = in_->price(a, b, c); }
std::string MemoEngine::name() const { return "memo(" + in_->name() + ")"; }
void MemoEngine::clear() { c_.clear(); }
}
