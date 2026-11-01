Implement include/market.hpp in src/: an Observer/Observable pair, a LazyObject in the style of QuantLib, a self-registering Factory and a Decorator. The header comments are the spec. You may add private members and helpers, and may change how `Observer` and `Observable` store each other, but keep every public name, base class and signature. `observe` and `stop_observing` stay protected and take a `shared_ptr<Observable>`. C++20, no external dependency.

Lifetime rules, all of which must hold under AddressSanitizer:
- An Observer can be destroyed while Observables it watches are alive, and the other way round, in any order. Nothing dangles.
- During `notify()`, an observer may call `stop_observing`, and may destroy itself or another observer of the same subject. Notification must stay safe: the observers that remain are each updated exactly once, those destroyed are not touched.
- A subject can be observed by the same observer through two paths (a diamond). `value()` of the top must recompute only once after a change at the bottom.

`REGISTER_ENGINE` must work from a translation unit of an executable linking this library statically, including when nothing else references that translation unit's symbols from the library side.
