#include "thread_pool.hpp"
#include <atomic>
#include <cstdio>
#include <vector>
using qm::ThreadPool;
static int fib(ThreadPool& p, int n) { if (n < 2) return n; auto f = p.submit([&p, n] { return fib(p, n - 1); }); int b = fib(p, n - 2); return p.wait(f) + b; }
int main() {
    for (int r = 0; r < 20; r++) {
        std::atomic<long> s{0};
        { ThreadPool p(8);
          std::vector<std::future<int>> v;
          for (int i = 0; i < 500; i++) v.push_back(p.submit([&, i] { s += i; return i; }));
          for (auto& f : v) f.get();
          p.parallel_for(0, 2000, [&](std::size_t i) { s += long(i); });
          if (fib(p, 12) != 144) return 2;
          for (int i = 0; i < 200; i++) p.submit([&] { s++; });
        }
        if (s != 124750 + 1999000 + 200) return 3;
    }
    puts("PASS tsan_clean");
}
