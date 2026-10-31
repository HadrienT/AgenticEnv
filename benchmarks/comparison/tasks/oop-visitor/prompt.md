Build a small instrument library around the classic double-dispatch Visitor pattern, in include/instruments.hpp and src/ (C++20, no external dependency). Everything is in `namespace inst`.

Market data:
    struct Market { double spot, rate, vol; };

Instruments, deriving from an abstract `Instrument` with `virtual void accept(Visitor&) const = 0;`, `virtual std::unique_ptr<Instrument> clone() const = 0;` and a virtual destructor:
- `EuropeanOption(double strike, double maturity, bool is_call)`
- `DigitalOption(double strike, double maturity, double cash)`: European cash-or-nothing call
- `BarrierOption(double strike, double barrier, double maturity)`: continuously monitored down-and-out call, with barrier < spot and barrier <= strike assumed
- `ZeroCouponBond(double maturity, double notional)`
- `Portfolio()`, the Composite: `void add(std::unique_ptr<Instrument> item, double quantity)`, and `std::size_t size() const`. A Portfolio can hold Portfolios. `accept` on a Portfolio calls `visit(const Portfolio&)` on the visitor only; visitors decide how to traverse, through `const std::vector<Position>& positions() const`, where `struct Position { std::unique_ptr<Instrument> item; double quantity; };`

Each concrete class exposes its constructor arguments as const getters with the same names: `strike()`, `maturity()`, `is_call()`, `cash()`, `barrier()`, `notional()`.

`Visitor` is abstract, with one pure virtual `void visit(const X&)` per concrete instrument: a visitor that forgets one instrument type must not compile when instantiated.

Visitors to provide:
- `PricingVisitor(Market m)`: closed-form Black-Scholes with continuous rate and no dividend (Rubinstein-Reiner for the barrier). `double result() const` is the value of the instrument last visited, quantities applied through a Portfolio.
- `DeltaVisitor(Market m)`: `double result() const`, derivative of value with respect to spot, within 1e-5 of the true value, same Portfolio rule.
- `JsonVisitor`: `std::string result() const`, compact JSON, fields in this exact order, numbers printed by `std::to_string` with trailing zeros then a trailing dot removed:
  `{"type":"european","strike":100,"maturity":1.5,"call":true}`
  `{"type":"digital","strike":100,"maturity":1,"cash":10}`
  `{"type":"barrier","strike":100,"barrier":80,"maturity":1}`
  `{"type":"zcb","maturity":2,"notional":1000}`
  `{"type":"portfolio","positions":[{"quantity":2,"item":{...}},...]}`

The visitors must not use dynamic_cast, typeid or a type enum: type-specific behaviour is reached by double dispatch only. A visitor object can be reused for several instruments: each `accept` replaces the previous result.
