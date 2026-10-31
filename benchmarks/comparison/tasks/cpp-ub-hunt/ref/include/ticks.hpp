#pragma once
#include <cstdint>
#include <span>
#include <string>
#include <string_view>
#include <vector>
namespace ticks {
struct Order { double px; int qty; };

// Upper-cased ticker. The result stays valid as long as `in`'s storage does not need to:
// callers keep the returned value after `in` is gone.
std::string upper_ticker(std::string_view in);
// Appends to `v` the negative of every element present on entry, in order.
void append_negated(std::vector<double>& v);
// 32-bit FNV-style mix, defined as arithmetic modulo 2^32 and returned as a signed bit pattern.
std::int32_t mix_hash(std::span<const std::int32_t> values);
// Reads the little-endian double stored at byte offset `off`, at any alignment.
double read_price(const unsigned char* buf, std::size_t off);
// Counts `per_thread` ticks on each of `threads` threads and returns the total.
long count_ticks(int threads, long per_thread);

class Book {
public:
    void add(Order o);
    const Order& best() const;     // highest px
    // Adds `o`, then returns best().px minus the px that was best before the call.
    double add_and_improvement(Order o);
private:
    std::vector<Order> orders_;
};

// Means of every full window of length w; out has values.size() - w + 1 elements.
std::vector<double> rolling_mean(const std::vector<double>& values, std::size_t w);
// "name:len": returns a label built from the name, and keeps a copy in `archive`.
std::string archive_label(std::string name, std::vector<std::string>& archive);
// Mask with the low `bits` bits set; bits ranges over 0..64.
std::uint64_t low_mask(int bits);
// Trimmed copy of the middle element of `words`, as a const reference valid until the next call.
std::string middle_word(const std::vector<std::string>& words);
}  // namespace ticks
