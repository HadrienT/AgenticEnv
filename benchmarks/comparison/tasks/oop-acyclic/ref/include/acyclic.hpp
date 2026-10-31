#pragma once
#include <stdexcept>
#include <string>
namespace trade {
struct VisitorBase { virtual ~VisitorBase() = default; };
template <class T> struct Visitor { virtual ~Visitor() = default; virtual void visit(const T&) = 0; };
class UnsupportedTrade : public std::runtime_error { public: using std::runtime_error::runtime_error; };
struct Trade { virtual ~Trade() = default; virtual void accept(VisitorBase&) const = 0; virtual bool try_accept(VisitorBase&) const = 0; virtual std::string type_name() const = 0; };
template <class D> struct VisitableTrade : Trade {
    bool try_accept(VisitorBase& v) const override { if (auto* p = dynamic_cast<Visitor<D>*>(&v)) { p->visit(static_cast<const D&>(*this)); return true; } return false; }
    void accept(VisitorBase& v) const override { if (!try_accept(v)) throw UnsupportedTrade("unsupported trade: " + this->type_name()); }
    std::string type_name() const override { return "Trade"; }
};
}
