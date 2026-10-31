#include "vec.hpp"
#include <cstdio>
using qm::Vec;
static auto make(const Vec& b) { return Vec(b.size(), 2.0) + Vec(b.size(), 1.0) + b; }
int main() {
    Vec b(100, 1.0);
    auto e = make(b);
    auto e2 = (b + Vec(100, 3.0)) * 2.0 - Vec(100, 1.0);
    Vec a = e; a = qm::shift(a, 7); a = a + e2;
    double s = qm::sum(a);
    if (s < 0) return 2;
    puts("PASS asan_clean");
}
