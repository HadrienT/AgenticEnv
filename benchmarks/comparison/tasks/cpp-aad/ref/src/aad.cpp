#include "aad.hpp"
#include <cmath>
namespace aad {
static const std::uint32_t NONE = 0xffffffffu;
Tape& Tape::active() { thread_local Tape t; return t; }
std::size_t Tape::size() const { return nodes.size(); }
void Tape::reserve(std::size_t n) { nodes.reserve(n); adj.reserve(n); adj.resize(0); }
Tape::Mark Tape::mark() const { return {nodes.size()}; }
void Tape::rewind(Mark m) { nodes.resize(m.pos); }
void Tape::clear() { nodes.clear(); adj.clear(); }
void Tape::reset_adjoints() { adj.assign(nodes.size(), 0.0); }
std::size_t Tape::rec(std::size_t a, double da, std::size_t b, double db) { nodes.push_back({std::uint32_t(a), std::uint32_t(b), da, db}); return nodes.size() - 1; }
void Tape::propagate(const Var& out) { reset_adjoints(); adj[out.id] = 1; for (std::size_t i = out.id + 1; i-- > 0;) { double w = adj[i]; if (w == 0) continue; auto& n = nodes[i]; if (n.a != NONE) adj[n.a] += w * n.da; if (n.b != NONE) adj[n.b] += w * n.db; } }
static Tape& T() { return Tape::active(); }
Var::Var(double v) : id(T().rec(NONE, 0, NONE, 0)), val(v) {}
double Var::value() const { return val; }
double Var::adjoint() const { auto& t = T(); return id < t.adj.size() ? t.adj[id] : 0.0; }
Var& Var::operator+=(const Var& o) { return *this = *this + o; }
Var& Var::operator-=(const Var& o) { return *this = *this - o; }
Var& Var::operator*=(const Var& o) { return *this = *this * o; }
Var& Var::operator/=(const Var& o) { return *this = *this / o; }
Var operator+(const Var& a, const Var& b) { return Var(a.val + b.val, T().rec(a.id, 1, b.id, 1)); }
Var operator-(const Var& a, const Var& b) { return Var(a.val - b.val, T().rec(a.id, 1, b.id, -1)); }
Var operator*(const Var& a, const Var& b) { return Var(a.val * b.val, T().rec(a.id, b.val, b.id, a.val)); }
Var operator/(const Var& a, const Var& b) { return Var(a.val / b.val, T().rec(a.id, 1 / b.val, b.id, -a.val / (b.val * b.val))); }
Var operator-(const Var& a) { return Var(-a.val, T().rec(a.id, -1, NONE, 0)); }
Var exp(const Var& a) { double e = std::exp(a.val); return Var(e, T().rec(a.id, e, NONE, 0)); }
Var log(const Var& a) { return Var(std::log(a.val), T().rec(a.id, 1 / a.val, NONE, 0)); }
Var sqrt(const Var& a) { double s = std::sqrt(a.val); return Var(s, T().rec(a.id, .5 / s, NONE, 0)); }
Var pow(const Var& a, double p) { return Var(std::pow(a.val, p), T().rec(a.id, p * std::pow(a.val, p - 1), NONE, 0)); }
Var normal_cdf(const Var& a) { return Var(.5 * std::erfc(-a.val * M_SQRT1_2), T().rec(a.id, std::exp(-.5 * a.val * a.val) / std::sqrt(2 * M_PI), NONE, 0)); }
Var max(const Var& a, const Var& b) { if (a.val >= b.val) return Var(a.val, T().rec(a.id, 1, NONE, 0)); return Var(b.val, T().rec(b.id, 1, NONE, 0)); }
}
