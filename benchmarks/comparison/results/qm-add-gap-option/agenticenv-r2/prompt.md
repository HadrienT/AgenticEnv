Add a gap option to the library, following the architecture of the repo: payoff in `instruments/`, engine in `engines/`, adapter and registry wiring in `pricers/`, dispatch through the existing instrument visitor, and tests.

A gap call pays (S_T - strike) if S_T > trigger, and a gap put pays (strike - S_T) if S_T < trigger. The payoff can be negative.

Exact names to use:
- `include/quantModeling/instruments/equity/gap.hpp`: `struct GapOption final : Instrument`, built as `GapOption(std::shared_ptr<const IPayoff> payoff, std::shared_ptr<const IExercise> exercise, Real trigger, Real notional = 1.0)`, with public fields `payoff`, `exercise`, `trigger`, `notional`.
- `IInstrumentVisitor` gets a `visit(const GapOption &)` overload that behaves as its other recent overloads do by default, so that the engines that do not support it refuse it and none needs editing.
- `include/quantModeling/engines/analytic/gap.hpp` and `src/engines/analytic/gap.cpp`: `class BSGapAnalyticEngine final : public EngineBase`, closed-form under Black-Scholes with dividend yield, filling the npv and the delta.
- `struct GapBSInput { Real spot; Real strike; Real trigger; Time maturity; Real rate; Real dividend; Real vol; bool is_call; };` in `pricers/inputs.hpp`.
- `InstrumentKind::EquityGapOption`, added at the end of the enum, available through `default_registry()` for `ModelKind::BlackScholes` and `EngineKind::Analytic`, with the adapter `price_equity_gap_bs_analytic` in `pricers/adapters/equity_gap.hpp` and `src/pricers/adapters/equity_gap.cpp`.
- A new test file `tests/testGap.cpp` registered in the build, with at least 3 tests.

It must compile and all the existing tests must keep passing.
