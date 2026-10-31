#pragma once
#include <algorithm>
#include <functional>
#include <map>
#include <tuple>
#include <memory>
#include <string>
#include <vector>
namespace mkt {
class Observer {
public:
    virtual ~Observer();
    virtual void update() = 0;
    friend class Observable;
protected:
    void observe(const std::shared_ptr<class Observable>& o);
    void stop_observing(const std::shared_ptr<class Observable>& o);
private:
    std::shared_ptr<struct Link> link_;
    std::vector<std::shared_ptr<class Observable>> subjects_;
};
class Observable {
public:
    virtual ~Observable();
    void notify();
    void add_(std::shared_ptr<struct Link> l);
    void remove_(struct Link* l);
private:
    std::vector<std::shared_ptr<struct Link>> links_;
};
// A mutable market value. set() with the current value does nothing.
class Quote : public Observable {
public:
    explicit Quote(double v);
    double value() const;
    void set(double v);
private:
    double v_;
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
private:
    mutable bool dirty_ = true; mutable bool sent_ = true; mutable double v_ = 0; mutable long n_ = 0;
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
private:
    std::map<std::string, std::function<std::unique_ptr<Engine>()>> m_;
};
#define REGISTER_CAT2(a, b) a##b
#define REGISTER_CAT(a, b) REGISTER_CAT2(a, b)
#define REGISTER_ENGINE(key, Class) static const bool REGISTER_CAT(reg_, __COUNTER__) = (::mkt::EngineFactory::instance().add(key, [] { return std::unique_ptr<::mkt::Engine>(new Class()); }), true)
// Decorator: same interface as the wrapped engine, caches price() by exact argument
// triple. clear() empties the cache. name() is "memo(" + wrapped name + ")".
class MemoEngine : public Engine {
public:
    explicit MemoEngine(std::unique_ptr<Engine> inner);
    double price(double spot, double strike, double vol) const override;
    std::string name() const override;
    void clear();
private:
    std::unique_ptr<Engine> in_; mutable std::map<std::tuple<double, double, double>, double> c_;
};
}  // namespace mkt
