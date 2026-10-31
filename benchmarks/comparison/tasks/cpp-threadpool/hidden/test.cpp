#include "thread_pool.hpp"
#include "chk.hpp"
#include <atomic>
#include <chrono>
#include <memory>
#include <numeric>
#include <set>
#include <stdexcept>
#include <thread>
#include <vector>
using qm::ThreadPool;
static int fib(ThreadPool& p, int n) {
    if (n < 2) return n;
    auto f = p.submit([&p, n] { return fib(p, n - 1); });
    int b = fib(p, n - 2);
    return p.wait(f) + b;
}
int main() {
    sec("returns_values", [] { ThreadPool p(4); std::vector<std::future<int>> v; for (int i = 0; i < 1000; i++) v.push_back(p.submit([i] { return i * 2; }));
        long s = 0; for (auto& f : v) s += f.get(); return s == 999 * 1000; });
    sec("args_and_move_only", [] { ThreadPool p(2);
        auto u = std::make_unique<int>(40);
        auto f = p.submit([u = std::move(u)](int x) { return *u + x; }, 2);
        auto g = p.submit([](std::unique_ptr<int> a) { return *a; }, std::make_unique<int>(7));
        auto h = p.submit([] {});
        h.get(); return f.get() == 42 && g.get() == 7; });
    sec("exception_in_future", [] { ThreadPool p(2); auto f = p.submit([]() -> int { throw std::runtime_error("x"); });
        try { f.get(); } catch (const std::runtime_error&) { return p.submit([] { return 1; }).get() == 1; } return false; });
    sec("drains_on_destruct", [] { std::atomic<int> c{0}; { ThreadPool p(1); for (int i = 0; i < 200; i++) p.submit([&c] { std::this_thread::sleep_for(std::chrono::microseconds(200)); c++; }); } return c == 200; });
    sec("nested_single_thread", [] { ThreadPool p(1);
        auto f = p.submit([&p] { auto g = p.submit([&p] { auto h = p.submit([] { return 5; }); return p.wait(h) + 1; }); return p.wait(g) + 1; });
        return p.wait(f) == 7; }, 20);
    sec("recursive_fib", [] { ThreadPool p(2); return fib(p, 18) == 2584; }, 60);
    sec("parallel_for_covers", [] { ThreadPool p(4); std::vector<std::atomic<int>> h(10000); p.parallel_for(0, 10000, [&](std::size_t i) { h[i]++; });
        for (auto& x : h) if (x != 1) return false;
        p.parallel_for(5, 5, [](std::size_t) { abort(); });
        return true; });
    sec("parallel_for_exception", [] { ThreadPool p(4);
        try { p.parallel_for(0, 1000, [](std::size_t i) { if (i == 777) throw std::out_of_range("x"); }); } catch (const std::out_of_range&) { return p.submit([] { return 3; }).get() == 3; }
        return false; }, 30);
    sec("parallel_for_nested", [] { ThreadPool p(1); std::atomic<int> c{0};
        auto f = p.submit([&] { p.parallel_for(0, 8, [&](std::size_t) { p.parallel_for(0, 8, [&](std::size_t) { c++; }); }); return 1; });
        p.wait(f); return c == 64; }, 30);
    sec("really_parallel", [] { ThreadPool p(4); std::atomic<int> here{0}, peak{0};
        p.parallel_for(0, 4, [&](std::size_t) { int n = ++here; int m = peak.load(); while (m < n && !peak.compare_exchange_weak(m, n)) {} std::this_thread::sleep_for(std::chrono::milliseconds(100)); --here; });
        fprintf(stderr, "peak %d\n", peak.load()); return peak >= 3; });
    return 0;
}
