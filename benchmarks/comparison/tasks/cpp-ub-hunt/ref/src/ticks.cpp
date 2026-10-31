#include "ticks.hpp"
#include <algorithm>
#include <atomic>
#include <cstring>
#include <cctype>
#include <numeric>
#include <stdexcept>
#include <thread>
namespace ticks {
std::string upper_ticker(std::string_view in) {
    std::string out(in);
    std::transform(out.begin(), out.end(), out.begin(), [](unsigned char c) { return char(std::toupper(c)); });
    return out;
}
void append_negated(std::vector<double>& v) {
    std::size_t n = v.size(); v.reserve(2 * n);
    for (std::size_t i = 0; i < n; i++) v.push_back(-v[i]);
}
std::int32_t mix_hash(std::span<const std::int32_t> values) {
    std::uint32_t h = 2166136261u;
    for (std::int32_t x : values) { h ^= std::uint32_t(x); h *= 16777619u; }
    return std::int32_t(h);
}
double read_price(const unsigned char* buf, std::size_t off) {
    double d; std::memcpy(&d, buf + off, sizeof d); return d;
}
long count_ticks(int threads, long per_thread) {
    std::atomic<long> total{0};
    std::vector<std::thread> pool;
    for (int t = 0; t < threads; t++)
        pool.emplace_back([&] { for (long i = 0; i < per_thread; i++) total++; });
    for (auto& t : pool) t.join();
    return total;
}
void Book::add(Order o) { orders_.push_back(o); }
const Order& Book::best() const {
    return *std::max_element(orders_.begin(), orders_.end(), [](const Order& a, const Order& b) { return a.px < b.px; });
}
double Book::add_and_improvement(Order o) {
    double before = best().px;
    add(o);
    return best().px - before;
}
std::vector<double> rolling_mean(const std::vector<double>& values, std::size_t w) {
    std::vector<double> out;
    double s = std::accumulate(values.begin(), values.begin() + w, 0.0);
    for (std::size_t i = w; i <= values.size(); i++) {
        out.push_back(s / double(w));
        if (i < values.size()) s += values[i] - values[i - w];
    }
    return out;
}
std::string archive_label(std::string name, std::vector<std::string>& archive) {
    archive.push_back(name);
    return name + ":" + std::to_string(name.size());
}
std::uint64_t low_mask(int bits) { return bits >= 64 ? ~std::uint64_t{0} : (std::uint64_t{1} << bits) - 1; }
std::string middle_word(const std::vector<std::string>& words) {
    std::string w = words[words.size() / 2];
    w.erase(0, w.find_first_not_of(' '));
    w.erase(w.find_last_not_of(' ') + 1);
    return w;
}
}  // namespace ticks
