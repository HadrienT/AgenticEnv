#include "ticks.hpp"
#include "chk.hpp"
#include <cstring>
#include <memory>
#include <string>
#include <vector>
using namespace ticks;
int main() {
    sec("dangling_view", [] {
        auto r = upper_ticker(std::string("msft.long.enough.to.defeat.small.string.opt"));
        auto r2 = upper_ticker(std::string("second.long.string.that.reuses.freed.storage"));
        return std::string(r) == "MSFT.LONG.ENOUGH.TO.DEFEAT.SMALL.STRING.OPT" && std::string(r2) == "SECOND.LONG.STRING.THAT.REUSES.FREED.STORAGE"; });
    sec("iterator_invalidation", [] { std::vector<double> v{1, 2, 3}; v.shrink_to_fit(); append_negated(v); return v == std::vector<double>{1, 2, 3, -1, -2, -3}; });
    sec("signed_overflow", [] { std::vector<std::int32_t> v{1, -2, 2000000000, 7}; std::uint32_t h = 2166136261u; for (auto x : v) { h ^= std::uint32_t(x); h *= 16777619u; } return mix_hash(v) == std::int32_t(h); });
    sec("misaligned_read", [] { unsigned char b[32] = {}; double x = 123.456; std::memcpy(b + 3, &x, 8); return read_price(b, 3) == x; });
    sec("reference_invalidation", [] { Book b; b.add({10, 1}); double d = b.add_and_improvement({12.5, 1}); double e = b.add_and_improvement({11, 1}); return near(d, 2.5, 1e-12) && near(e, 0, 1e-12); });
    sec("buffer_overread", [] { std::vector<double> v{1, 2, 3, 4}; v.shrink_to_fit(); auto m = rolling_mean(v, 2);
        std::vector<double> w{5}; w.shrink_to_fit(); auto n = rolling_mean(w, 1);
        return m == std::vector<double>{1.5, 2.5, 3.5} && n == std::vector<double>{5}; });
    sec("use_after_move", [] { std::vector<std::string> a; auto s = archive_label("instrument-name-long-enough-for-heap", a); return s == "instrument-name-long-enough-for-heap:36" && a.size() == 1 && a[0] == "instrument-name-long-enough-for-heap"; });
    sec("shift_too_wide", [] { return low_mask(0) == 0 && low_mask(1) == 1 && low_mask(63) == 0x7fffffffffffffffULL && low_mask(64) == ~0ULL; });
    sec("returned_local_ref", [] { std::vector<std::string> w{"a", "  long enough middle word for heap  ", "c"}; const auto& r = middle_word(w); std::string other(64, 'x'); return r == "long enough middle word for heap"; });
    sec("behaviour_kept", [] { Book b; b.add({1, 1}); b.add({3, 1}); b.add({2, 1}); return b.best().px == 3 && upper_ticker("aB") == "AB"; });
    return 0;
}
