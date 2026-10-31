#pragma once
#include <atomic>
#include <condition_variable>
#include <cstddef>
#include <deque>
#include <exception>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <thread>
#include <tuple>
#include <type_traits>
#include <vector>
namespace qm {
class ThreadPool {
public:
    explicit ThreadPool(std::size_t threads);
    ~ThreadPool();
    ThreadPool(const ThreadPool&) = delete;
    ThreadPool& operator=(const ThreadPool&) = delete;
    template <class F, class... A>
    auto submit(F&& f, A&&... args) -> std::future<std::invoke_result_t<std::decay_t<F>, std::decay_t<A>...>> {
        using R = std::invoke_result_t<std::decay_t<F>, std::decay_t<A>...>;
        auto t = std::make_shared<std::packaged_task<R()>>([fn = std::forward<F>(f), tup = std::make_tuple(std::forward<A>(args)...)]() mutable -> R { return std::apply(std::move(fn), std::move(tup)); });
        auto fut = t->get_future();
        { std::lock_guard l(m_); q_.push_back([t] { (*t)(); }); }
        cv_.notify_all();
        return fut;
    }
    template <class T> T wait(std::future<T>& fut) {
        while (fut.wait_for(std::chrono::seconds(0)) != std::future_status::ready) if (!run_one()) std::this_thread::yield();
        return fut.get();
    }
    void parallel_for(std::size_t begin, std::size_t end, const std::function<void(std::size_t)>& body);
private:
    bool run_one();
    std::mutex m_; std::condition_variable cv_; std::deque<std::function<void()>> q_; bool stop_ = false; std::vector<std::thread> w_;
};
}
