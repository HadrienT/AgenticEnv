The classic Visitor couples the base class to every concrete type: adding a new trade means recompiling every visitor. Implement an **Acyclic Visitor** in C++20, in `namespace trade`, so third parties can add both new trades and new visitors in their own translation units, without editing or recompiling this library.

include/acyclic.hpp, the framework. It must not mention any concrete trade:
- `struct VisitorBase` : polymorphic, empty marker.
- `template <class T> struct Visitor` : abstract, `virtual void visit(const T&) = 0;`
- `struct Trade`: abstract, `virtual void accept(VisitorBase&) const = 0;`, `virtual bool try_accept(VisitorBase&) const = 0;`, `virtual std::string type_name() const = 0;`, virtual destructor.
- `template <class Derived> struct VisitableTrade : Trade` (CRTP): implements `accept`, which calls `visit` when the visitor supports `Derived` and throws `trade::UnsupportedTrade` otherwise; and `try_accept`, the same, returning false instead of throwing. It has a default `type_name()`, overridable by `Derived`.
- `class UnsupportedTrade : public std::runtime_error`: its `what()` contains `type_name()`.

include/trades.hpp and src/trades.cpp, the library's own content:
- `struct Swap : VisitableTrade<Swap> { Swap(double notional, double rate); double notional, rate; std::string type_name() const override; };`, with type_name "Swap"
- `struct Bond : VisitableTrade<Bond> { Bond(double face); double face; std::string type_name() const override; };`, with type_name "Bond"
- `class NotionalVisitor : public VisitorBase, public Visitor<Swap>, public Visitor<Bond>`, compiled in src/trades.cpp. `double total() const` accumulates swap notionals and bond faces over all the trades visited.

Keep the virtual functions of NotionalVisitor overridable: a derived class must be able to add support for a new trade with multiple inheritance.
