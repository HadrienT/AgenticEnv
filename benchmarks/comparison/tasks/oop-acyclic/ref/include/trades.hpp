#pragma once
#include "acyclic.hpp"
namespace trade {
struct Swap : VisitableTrade<Swap> { Swap(double n, double r); double notional, rate; std::string type_name() const override; };
struct Bond : VisitableTrade<Bond> { Bond(double f); double face; std::string type_name() const override; };
class NotionalVisitor : public VisitorBase, public Visitor<Swap>, public Visitor<Bond> { public: void visit(const Swap&) override; void visit(const Bond&) override; double total() const; private: double t_ = 0; };
}
