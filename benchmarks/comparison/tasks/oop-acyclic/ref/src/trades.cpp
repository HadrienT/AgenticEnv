#include "trades.hpp"
namespace trade {
Swap::Swap(double n, double r) : notional(n), rate(r) {}
std::string Swap::type_name() const { return "Swap"; }
Bond::Bond(double f) : face(f) {}
std::string Bond::type_name() const { return "Bond"; }
void NotionalVisitor::visit(const Swap& s) { t_ += s.notional; }
void NotionalVisitor::visit(const Bond& b) { t_ += b.face; }
double NotionalVisitor::total() const { return t_; }
}
