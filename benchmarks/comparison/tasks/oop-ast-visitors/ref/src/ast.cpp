#include "ast.hpp"
#include <cmath>
#include <cstdio>
#include <stdexcept>
#include <vector>
namespace ast {
struct Num; struct Var; struct Add; struct Sub; struct Mul; struct Neg; struct Pow; struct Exp; struct Log;
struct Visitor { virtual ~Visitor() = default; virtual void v(const Num&) = 0; virtual void v(const Var&) = 0; virtual void v(const Add&) = 0; virtual void v(const Sub&) = 0; virtual void v(const Mul&) = 0; virtual void v(const Neg&) = 0; virtual void v(const Pow&) = 0; virtual void v(const Exp&) = 0; virtual void v(const Log&) = 0; };
#define N(T) struct T : Node { void accept(Visitor& x) const override { x.v(*this); } };
N(Num) N(Var) N(Add) N(Sub) N(Mul) N(Neg) N(Pow) N(Exp) N(Log)
Node::~Node() { std::vector<Ptr> s; if (a) s.push_back(std::move(a)); if (b) s.push_back(std::move(b)); while (!s.empty()) { Ptr p = std::move(s.back()); s.pop_back(); if (p->a) s.push_back(std::move(p->a)); if (p->b) s.push_back(std::move(p->b)); } }
template <class T> static Ptr mk(Ptr a = nullptr, Ptr b = nullptr) { auto p = std::make_unique<T>(); p->a = std::move(a); p->b = std::move(b); return p; }
Ptr num(double v) { auto p = mk<Num>(); p->value = v; return p; }
Ptr var(std::string n) { auto p = mk<Var>(); p->name = std::move(n); return p; }
Ptr add(Ptr a, Ptr b) { return mk<Add>(std::move(a), std::move(b)); }
Ptr sub(Ptr a, Ptr b) { return mk<Sub>(std::move(a), std::move(b)); }
Ptr mul(Ptr a, Ptr b) { return mk<Mul>(std::move(a), std::move(b)); }
Ptr neg(Ptr a) { return mk<Neg>(std::move(a)); }
Ptr pow_(Ptr a, double e) { auto p = mk<Pow>(std::move(a)); p->value = e; return p; }
Ptr exp_(Ptr a) { return mk<Exp>(std::move(a)); }
Ptr log_(Ptr a) { return mk<Log>(std::move(a)); }
struct Eval : Visitor { const Env& e; double r = 0; Eval(const Env& x) : e(x) {} double go(const Node& n) { n.accept(*this); return r; }
    void v(const Num& n) override { r = n.value; } void v(const Var& n) override { r = e.at(n.name); } void v(const Add& n) override { double x = go(*n.a); r = x + go(*n.b); } void v(const Sub& n) override { double x = go(*n.a); r = x - go(*n.b); } void v(const Mul& n) override { double x = go(*n.a); r = x * go(*n.b); } void v(const Neg& n) override { r = -go(*n.a); } void v(const Pow& n) override { r = std::pow(go(*n.a), n.value); } void v(const Exp& n) override { r = std::exp(go(*n.a)); } void v(const Log& n) override { r = std::log(go(*n.a)); } };
double eval(const Node& n, const Env& e) { Eval x(e); return x.go(n); }
struct Prec : Visitor { int p = 0; void v(const Num& n) override { p = n.value < 0 ? 3 : 5; } void v(const Var&) override { p = 5; } void v(const Add&) override { p = 1; } void v(const Sub&) override { p = 1; } void v(const Mul&) override { p = 2; } void v(const Neg&) override { p = 3; } void v(const Pow&) override { p = 4; } void v(const Exp&) override { p = 5; } void v(const Log&) override { p = 5; } };
static int prec(const Node& n) { Prec x; n.accept(x); return x.p; }
struct Print : Visitor { std::string s; std::string go(const Node& n) { n.accept(*this); return s; } std::string par(const Node& n, bool w) { auto t = go(n); return w ? "(" + t + ")" : t; }
    void v(const Num& n) override { char b[64]; snprintf(b, 64, "%g", n.value); s = b; } void v(const Var& n) override { s = n.name; }
    void bin(const Node& n, const char* op, int p) { auto l = par(*n.a, prec(*n.a) < p); auto r = par(*n.b, prec(*n.b) <= p); s = l + op + r; }
    void v(const Add& n) override { bin(n, " + ", 1); } void v(const Sub& n) override { bin(n, " - ", 1); } void v(const Mul& n) override { bin(n, " * ", 2); }
    void v(const Neg& n) override { s = "-" + par(*n.a, prec(*n.a) < 3); } void v(const Pow& n) override { char b[64]; snprintf(b, 64, "%g", n.value); s = par(*n.a, prec(*n.a) <= 4) + "^" + b; } void v(const Exp& n) override { s = "exp(" + go(*n.a) + ")"; } void v(const Log& n) override { s = "log(" + go(*n.a) + ")"; } };
std::string print(const Node& n) { Print p; return p.go(n); }
struct Vars : Visitor { std::set<std::string> s; void g(const Node& n) { n.accept(*this); } void v(const Num&) override {} void v(const Var& n) override { s.insert(n.name); } void v(const Add& n) override { g(*n.a); g(*n.b); } void v(const Sub& n) override { g(*n.a); g(*n.b); } void v(const Mul& n) override { g(*n.a); g(*n.b); } void v(const Neg& n) override { g(*n.a); } void v(const Pow& n) override { g(*n.a); } void v(const Exp& n) override { g(*n.a); } void v(const Log& n) override { g(*n.a); } };
std::set<std::string> vars(const Node& n) { Vars x; n.accept(x); return x.s; }
struct Clone : Visitor { Ptr r; Ptr go(const Node& n) { n.accept(*this); return std::move(r); } void v(const Num& n) override { r = num(n.value); } void v(const Var& n) override { r = var(n.name); } void v(const Add& n) override { auto a = go(*n.a); r = add(std::move(a), go(*n.b)); } void v(const Sub& n) override { auto a = go(*n.a); r = sub(std::move(a), go(*n.b)); } void v(const Mul& n) override { auto a = go(*n.a); r = mul(std::move(a), go(*n.b)); } void v(const Neg& n) override { r = neg(go(*n.a)); } void v(const Pow& n) override { r = pow_(go(*n.a), n.value); } void v(const Exp& n) override { r = exp_(go(*n.a)); } void v(const Log& n) override { r = log_(go(*n.a)); } };
Ptr clone(const Node& n) { Clone c; return c.go(n); }
struct IsNum : Visitor { bool y = false; double d = 0; void v(const Num& n) override { y = true; d = n.value; } void v(const Var&) override {} void v(const Add&) override {} void v(const Sub&) override {} void v(const Mul&) override {} void v(const Neg&) override {} void v(const Pow&) override {} void v(const Exp&) override {} void v(const Log&) override {} };
struct IsNeg : IsNum { const Node* in = nullptr; void v(const Neg& n) override { in = n.a.get(); } };
static bool isnum(const Node& n, double& d) { IsNum x; n.accept(x); d = x.d; return x.y; }
struct Fold : Visitor { Ptr r; Ptr go(const Node& n) { n.accept(*this); return std::move(r); } void v(const Num& n) override { r = num(n.value); } void v(const Var& n) override { r = var(n.name); }
    void v(const Add& n) override { auto a = go(*n.a), b = go(*n.b); double x, y; bool p = isnum(*a, x), q = isnum(*b, y); if (p && q) r = num(x + y); else if (p && x == 0) r = std::move(b); else if (q && y == 0) r = std::move(a); else r = add(std::move(a), std::move(b)); }
    void v(const Sub& n) override { auto a = go(*n.a), b = go(*n.b); double x, y; bool p = isnum(*a, x), q = isnum(*b, y); if (p && q) r = num(x - y); else if (q && y == 0) r = std::move(a); else if (p && x == 0) { auto t = neg(std::move(b)); r = go(*t); } else r = sub(std::move(a), std::move(b)); }
    void v(const Mul& n) override { auto a = go(*n.a), b = go(*n.b); double x, y; bool p = isnum(*a, x), q = isnum(*b, y); if (p && q) r = num(x * y); else if ((p && x == 0) || (q && y == 0)) r = num(0); else if (p && x == 1) r = std::move(b); else if (q && y == 1) r = std::move(a); else r = mul(std::move(a), std::move(b)); }
    void v(const Neg& n) override { auto a = go(*n.a); double x; if (isnum(*a, x)) { r = num(-x); return; } IsNeg k; a->accept(k); if (k.in) { r = clone(*k.in); return; } r = neg(std::move(a)); }
    void v(const Pow& n) override { auto a = go(*n.a); double x; if (n.value == 0) r = num(1); else if (isnum(*a, x)) r = num(std::pow(x, n.value)); else if (n.value == 1) r = std::move(a); else r = pow_(std::move(a), n.value); }
    void v(const Exp& n) override { auto a = go(*n.a); double x; r = isnum(*a, x) ? num(std::exp(x)) : exp_(std::move(a)); }
    void v(const Log& n) override { auto a = go(*n.a); double x; r = isnum(*a, x) ? num(std::log(x)) : log_(std::move(a)); } };
Ptr fold(const Node& n) { Fold f; return f.go(n); }
struct Diff : Visitor { std::string x; Ptr r; Ptr go(const Node& n) { n.accept(*this); return std::move(r); } void v(const Num&) override { r = num(0); } void v(const Var& n) override { r = num(n.name == x ? 1 : 0); }
    void v(const Add& n) override { auto a = go(*n.a); r = add(std::move(a), go(*n.b)); } void v(const Sub& n) override { auto a = go(*n.a); r = sub(std::move(a), go(*n.b)); }
    void v(const Mul& n) override { auto da = go(*n.a); auto db = go(*n.b); r = add(mul(std::move(da), clone(*n.b)), mul(clone(*n.a), std::move(db))); } void v(const Neg& n) override { r = neg(go(*n.a)); }
    void v(const Pow& n) override { r = mul(mul(num(n.value), pow_(clone(*n.a), n.value - 1)), go(*n.a)); } void v(const Exp& n) override { r = mul(exp_(clone(*n.a)), go(*n.a)); } void v(const Log& n) override { r = mul(go(*n.a), pow_(clone(*n.a), -1)); } };
Ptr diff(const Node& n, const std::string& x) { Diff d; d.x = x; return d.go(n); }
}
