#pragma once
#include <functional>
#include <memory>
#include <string>
#include <vector>
namespace mkt {
class Observer {
public:
    virtual ~Observer();
    virtual void update() = 0;
protected:
    void observe(const std::shared_ptr<class Observable>& o);
    void stop_observing(const std::shared_ptr<class Observable>& o);
};
class Observable {
public:
    virtual ~Observable();
    void notify();
};
// A mutable market value. set() with the current value does nothing.
class Quote : public Observable {
public:
    explicit Quote(double v);
    double value() const;
    void set(double v);
};
// Lazily computed value. value() recomputes only if a dependency changed since the last
// computation; a LazyObject that was invalidated forwards the notification once to its
// own observers, and does not forward again until it has been recomputed.
class LazyObject : public Observer, public Observable {
public:
    double value() const;
    long computations() const;   // how many times compute() ran
    void update() override;
protected:
    virtual double compute() const = 0;
};
// Black-Scholes forward-free price model used by tests.
struct Engine {
    virtual ~Engine() = default;
    virtual double price(double spot, double strike, double vol) const = 0;
    virtual std::string name() const = 0;
};
// Name -> maker registry. REGISTER_ENGINE(key, Class), used at namespace scope in any
// translation unit, makes create(key) return a new Class. Built in: "intrinsic" prices
// max(spot - strike, 0) + vol, and "flat" prices strike.
class EngineFactory {
public:
    static EngineFactory& instance();
    void add(const std::string& key, std::function<std::unique_ptr<Engine>()> maker);
    std::unique_ptr<Engine> create(const std::string& key) const;   // std::invalid_argument if unknown
    std::vector<std::string> keys() const;                          // sorted
};
// Decorator: same interface as the wrapped engine, caches price() by exact argument
// triple. clear() empties the cache. name() is "memo(" + wrapped name + ")".
class MemoEngine : public Engine {
public:
    explicit MemoEngine(std::unique_ptr<Engine> inner);
    double price(double spot, double strike, double vol) const override;
    std::string name() const override;
    void clear();
};
}  // namespace mkt
