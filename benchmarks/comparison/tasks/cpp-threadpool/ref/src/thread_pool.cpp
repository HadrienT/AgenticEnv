#include "thread_pool.hpp"
namespace qm {
ThreadPool::ThreadPool(std::size_t n) { for (std::size_t i = 0; i < n; i++) w_.emplace_back([this] { for (;;) { std::function<void()> t; { std::unique_lock l(m_); cv_.wait(l, [this] { return stop_ || !q_.empty(); }); if (q_.empty()) return; t = std::move(q_.front()); q_.pop_front(); } t(); } }); }
ThreadPool::~ThreadPool() { { std::lock_guard l(m_); stop_ = true; } cv_.notify_all(); for (auto& t : w_) t.join(); }
bool ThreadPool::run_one() { std::function<void()> t; { std::lock_guard l(m_); if (q_.empty()) return false; t = std::move(q_.front()); q_.pop_front(); } t(); return true; }
void ThreadPool::parallel_for(std::size_t b, std::size_t e, const std::function<void(std::size_t)>& body) {
    std::vector<std::future<void>> fs; for (std::size_t i = b; i < e; i++) fs.push_back(submit([&body, i] { body(i); }));
    std::exception_ptr first; for (auto& f : fs) { try { wait(f); } catch (...) { if (!first) first = std::current_exception(); } }
    if (first) std::rethrow_exception(first);
}
}
