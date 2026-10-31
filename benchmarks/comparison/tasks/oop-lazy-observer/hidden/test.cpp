#include <algorithm>
#include "market.hpp"
#include "chk.hpp"
#include <cmath>
#include <memory>
#include <vector>
using namespace mkt;
struct Px : LazyObject { std::shared_ptr<Quote> s, v; Px(std::shared_ptr<Quote> a, std::shared_ptr<Quote> b) : s(a), v(b) { observe(s); observe(v); } double compute() const override { return s->value() * v->value(); } using Observer::stop_observing; };
struct Sum : LazyObject { std::vector<std::shared_ptr<LazyObject>> p; Sum(std::vector<std::shared_ptr<LazyObject>> a) : p(std::move(a)) { for (auto& x : p) observe(x); } double compute() const override { double t = 0; for (auto& x : p) t += x->value(); return t; } };
struct Cnt : Observer { std::shared_ptr<Observable> o; int n = 0; explicit Cnt(std::shared_ptr<Observable> a) : o(a) { observe(o); } void update() override { n++; } };
struct Quitter : Observer { std::shared_ptr<Observable> o; int n = 0; explicit Quitter(std::shared_ptr<Observable> a) : o(a) { observe(o); } void update() override { n++; stop_observing(o); } };
struct Killer : Observer { std::unique_ptr<Observer>* victim; std::shared_ptr<Observable> o; int n = 0; Killer(std::shared_ptr<Observable> a, std::unique_ptr<Observer>* v) : victim(v), o(a) { observe(o); } void update() override { n++; victim->reset(); } };
struct Toy : Engine { double price(double a, double, double) const override { calls()++; return a * 2; } std::string name() const override { return "toy"; } static int& calls() { static int c = 0; return c; } };
REGISTER_ENGINE("third.party", Toy);
int main() {
    sec("lazy_recompute", [] { auto a = std::make_shared<Quote>(2), b = std::make_shared<Quote>(3); Px p(a, b); bool z = p.computations() == 0; double x = p.value(), y = p.value(); bool c1 = p.computations() == 1; a->set(5); bool c2 = p.computations() == 1; double w = p.value(); return z && c1 && c2 && x == 6 && y == 6 && w == 15 && p.computations() == 2; });
    sec("same_value_no_invalidate", [] { auto a = std::make_shared<Quote>(2), b = std::make_shared<Quote>(3); Px p(a, b); Cnt c(a); p.value(); a->set(2); a->set(2); p.value(); return p.computations() == 1 && c.n == 0; });
    sec("diamond_single_recalc", [] { auto s = std::make_shared<Quote>(2), u = std::make_shared<Quote>(1); auto l = std::make_shared<Px>(s, u), r = std::make_shared<Px>(s, s); auto top = std::make_shared<Sum>(std::vector<std::shared_ptr<LazyObject>>{l, r}); auto dbl = std::make_shared<Sum>(std::vector<std::shared_ptr<LazyObject>>{top, top}); double v0 = dbl->value(); bool a = v0 == 12; s->set(3); double v1 = dbl->value(); return a && v1 == 24 && top->computations() == 2 && dbl->computations() == 2 && r->computations() == 2; });
    sec("chain_propagates", [] { auto s = std::make_shared<Quote>(1), u = std::make_shared<Quote>(1); auto l = std::make_shared<Px>(s, u); auto t = std::make_shared<Sum>(std::vector<std::shared_ptr<LazyObject>>{l}); auto top = std::make_shared<Sum>(std::vector<std::shared_ptr<LazyObject>>{t}); Cnt c(top); top->value(); s->set(2); s->set(3); s->set(4); bool once = c.n == 1 && l->computations() == 1; bool ok = top->value() == 4; s->set(5); return once && ok && c.n == 2; });
    sec("observer_dies_first", [] { auto q = std::make_shared<Quote>(1); { Cnt a(q), b(q); q->set(2); } q->set(3); auto c = std::make_unique<Cnt>(q); q->set(4); int n = c->n; c.reset(); q->notify(); return n == 1; });
    sec("observable_dies_first", [] { auto* c = new Cnt(std::make_shared<Quote>(1)); c->o.reset(); delete c; std::unique_ptr<Cnt> d; { auto q = std::make_shared<Quote>(1); d = std::make_unique<Cnt>(q); d->o.reset(); q->set(2); } d.reset(); return true; });
    sec("unregister_during_notify", [] { auto q = std::make_shared<Quote>(1); Cnt a(q); Quitter z(q); Cnt b(q); q->set(2); q->set(3); bool quit = z.n == 1 && a.n == 2 && b.n == 2;
        std::unique_ptr<Observer> victim, v2, v3; int* dummy = nullptr; (void)dummy; v2 = std::make_unique<Cnt>(q); Killer k1(q, &victim); victim = std::make_unique<Cnt>(q); Killer k2(q, &v2); auto* raw3 = new Cnt(q); v3.reset(raw3); Killer k3(q, &v3); q->set(4); return quit && k1.n == 1 && k2.n == 1 && k3.n == 1 && a.n == 3; });
    sec("factory_builtin", [] { auto& f = EngineFactory::instance(); auto i = f.create("intrinsic"), l = f.create("flat"); return near(i->price(110, 100, .2), 10.2, 1e-12) && near(i->price(90, 100, .2), .2, 1e-12) && near(l->price(1, 77, 1), 77, 0); });
    sec("factory_unknown_throws", [] { try { EngineFactory::instance().create("nope"); } catch (const std::invalid_argument&) { return true; } return false; });
    sec("third_party_registration", [] { auto& f = EngineFactory::instance(); auto k = f.keys(); auto t = f.create("third.party"); return t->name() == "toy" && std::is_sorted(k.begin(), k.end()) && std::find(k.begin(), k.end(), "third.party") != k.end() && std::find(k.begin(), k.end(), "intrinsic") != k.end(); });
    sec("decorator_memoizes", [] { Toy::calls() = 0; MemoEngine m(std::make_unique<Toy>()); double a = m.price(2, 1, 1), b = m.price(2, 1, 1), c = m.price(2, 1, 2), d = m.price(3, 1, 1); Engine& e = m; return a == 4 && b == 4 && c == 4 && d == 6 && Toy::calls() == 3 && e.name() == "memo(toy)"; });
    sec("decorator_invalidate", [] { Toy::calls() = 0; MemoEngine m(std::make_unique<Toy>()); m.price(1, 1, 1); m.clear(); m.price(1, 1, 1); MemoEngine two(std::make_unique<MemoEngine>(std::make_unique<Toy>())); two.price(4, 4, 4); return Toy::calls() == 3 && two.name() == "memo(memo(toy))"; });
    return 0;
}
