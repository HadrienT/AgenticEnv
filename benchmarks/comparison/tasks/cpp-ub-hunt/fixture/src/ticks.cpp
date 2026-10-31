#include "ticks.hpp"
#include <algorithm>
#include <cctype>
#include <numeric>
#include <stdexcept>
#include <thread>
namespace ticks {
std::string_view upper_ticker(std::string_view in) {
    std::string out(in);
    std::transform(out.begin(), out.end(), out.begin(), [](unsigned char c) { return char(std::toupper(c)); });
    return out;
}
void append_negated(std::vector<double>& v) {
    for (auto it = v.begin(), e = v.end(); it != e; ++it) v.push_back(-*it);
}
std::int32_t mix_hash(std::span<const std::int32_t> values) {
    std::int32_t h = 2166136261u;
    for (std::int32_t x : values) { h ^= x; h *= 16777619; }
    return h;
}
double read_price(const unsigned char* buf, std::size_t off) {
    return *reinterpret_cast<const double*>(buf + off);
}
long count_ticks(int threads, long per_thread) {
    long total = 0;
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
    const Order& before = best();
    add(o);
    return best().px - before.px;
}
std::vector<double> rolling_mean(const std::vector<double>& values, std::size_t w) {
    std::vector<double> out;
    double s = std::accumulate(values.begin(), values.begin() + w, 0.0);
    for (std::size_t i = w; i <= values.size(); i++) {
        out.push_back(s / double(w));
        s += values[i] - values[i - w];
    }
    return out;
}
std::string archive_label(std::string name, std::vector<std::string>& archive) {
    archive.push_back(std::move(name));
    return name + ":" + std::to_string(name.size());
}
std::uint64_t low_mask(int bits) { return (std::uint64_t{1} << bits) - 1; }
const std::string& middle_word(const std::vector<std::string>& words) {
    std::string w = words[words.size() / 2];
    w.erase(0, w.find_first_not_of(' '));
    w.erase(w.find_last_not_of(' ') + 1);
    return w;
}
}  // namespace ticks
