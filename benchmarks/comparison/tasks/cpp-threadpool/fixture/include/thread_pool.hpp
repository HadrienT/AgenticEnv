#pragma once
#include <cstddef>
#include <functional>
#include <future>
#include <type_traits>
namespace qm {
class ThreadPool {
public:
    explicit ThreadPool(std::size_t threads);
    ~ThreadPool();  // runs everything still queued, then joins
    ThreadPool(const ThreadPool&) = delete;
    ThreadPool& operator=(const ThreadPool&) = delete;

    // Schedules f(args...). The callable and its arguments may be move-only.
    template <class F, class... A>
    auto submit(F&& f, A&&... args) -> std::future<std::invoke_result_t<std::decay_t<F>, std::decay_t<A>...>>;

    // Blocks until the future is ready. May be called from inside a task: while it
    // waits it runs queued tasks, so a task waiting on a child never deadlocks,
    // even with a single worker.
    template <class T>
    T wait(std::future<T>& fut);

    // Runs body(i) for i in [begin, end), blocks until done, and rethrows the first
    // exception a body threw. Same no-deadlock guarantee from inside a task.
    void parallel_for(std::size_t begin, std::size_t end, const std::function<void(std::size_t)>& body);
};
}  // namespace qm
