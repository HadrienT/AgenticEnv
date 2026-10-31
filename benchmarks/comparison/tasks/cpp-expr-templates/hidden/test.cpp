#include "vec.hpp"
#include "chk.hpp"
#include <atomic>
#include <cstdlib>
#include <new>
#include <string>
#include <vector>
using qm::Vec;
static std::atomic<long> allocs{0};
void* operator new(std::size_t n) { allocs++; void* p = malloc(n); if (!p) throw std::bad_alloc(); return p; }
void* operator new[](std::size_t n) { allocs++; void* p = malloc(n); if (!p) throw std::bad_alloc(); return p; }
void operator delete(void* p) noexcept { free(p); }
void operator delete[](void* p) noexcept { free(p); }
void operator delete(void* p, std::size_t) noexcept { free(p); }
void operator delete[](void* p, std::size_t) noexcept { free(p); }
static Vec mk(std::size_t n, double base) { Vec v(n); for (std::size_t i = 0; i < n; i++) v[i] = base + double(i); return v; }
template <class A, class B> concept CanAdd = requires(A a, B b) { a + b; };
auto localTemp(const Vec& b) { return (Vec(b.size(), 1.0) + Vec(b.size(), 2.0)) * 3.0 + b; }
int main() {
    sec("basic_values", [] {
        Vec a(4), b = mk(4, 1), c = mk(4, 2), d = mk(4, 3);
        a = b + c * 2.0 - d;
        Vec e(4); e = -(b - c) / 2.0 + 2.0 * d;
        for (int i = 0; i < 4; i++) {
            if (!near(a[i], (1 + i) + (2 + i) * 2.0 - (3 + i), 1e-12)) return false;
            if (!near(e[i], .5 + 2.0 * (3 + i), 1e-12)) return false;
        }
        return true; });
    sec("no_temporaries", [] {
        Vec a(1000), b = mk(1000, 1), c = mk(1000, 2), d = mk(1000, 3);
        long before = allocs;
        a = b + c * 2.0 - d;
        a = -a + b / 2.0;
        long after = allocs;
        if (after != before) { fprintf(stderr, "allocs %ld\n", after - before); return false; }
        before = allocs;
        Vec x = b + c * 2.0 - d;
        after = allocs;
        fprintf(stderr, "ctor allocs %ld\n", after - before);
        return after - before == 1 && x[0] == 2.0; });
    sec("auto_keeps_temporaries", [] {
        Vec b = mk(5, 1);
        auto e1 = Vec(5, 1.0) + b;
        auto e2 = (b + Vec(5, 2.0)) * 2.0;
        auto e3 = localTemp(b);
        Vec junk(5, 99.0); junk = junk + junk;
        Vec r1 = e1, r2 = e2, r3 = e3;
        for (int i = 0; i < 5; i++) {
            if (!near(r1[i], 2.0 + i, 1e-12) || !near(r2[i], 2.0 * (3 + i), 1e-12) || !near(r3[i], 9.0 + 1 + i, 1e-12)) return false;
        }
        return true; });
    sec("aliasing_elementwise", [] {
        Vec a = mk(50, 1), b = mk(50, 2);
        long before = allocs;
        a = a + b;
        a = b - a;
        long after = allocs;
        for (int i = 0; i < 50; i++) if (!near(a[i], (2 + i) - ((1 + i) + (2 + i)), 1e-12)) return false;
        return after == before; });
    sec("aliasing_shifted_view", [] {
        Vec a = mk(10, 0), o = a;
        a = qm::shift(a, 1);
        for (int i = 0; i < 10; i++) if (!near(a[i], o[(i + 1) % 10], 1e-12)) return false;
        Vec b = mk(7, 0);
        b = qm::shift(b, 3) + b;
        for (int i = 0; i < 7; i++) if (!near(b[i], (i + 3) % 7 + i, 1e-12)) return false;
        return true; });
    sec("size_mismatch", [] {
        Vec a(3), b(4), c(3);
        try { c = a + b; } catch (const std::invalid_argument&) { 
            try { Vec e(3), f(4); e = f; (void)e; } catch (const std::invalid_argument&) { return true; } catch (...) { return false; }
            return true; }
        return false; });
    sec("concept_accepts", [] {
        Vec a(2);
        auto e = a + a;
        return qm::VecExpr<Vec> && qm::VecExpr<decltype(e)> && qm::VecExpr<decltype(e * 2.0)> && qm::VecExpr<decltype(-e)>; });
    sec("concept_rejects", [] {
        return !qm::VecExpr<double> && !qm::VecExpr<int> && !qm::VecExpr<std::string> && !qm::VecExpr<std::vector<double>> &&
               !CanAdd<Vec, int> && !CanAdd<Vec, std::string> && !CanAdd<int, Vec> && !CanAdd<Vec, double>; });
    sec("reductions", [] {
        Vec a = mk(4, 1), b = mk(4, 2);
        return near(qm::sum(a + b), 10 + 14, 1e-12) && near(qm::dot(a, b * 2.0), 2 * (1*2 + 2*3 + 3*4 + 4*5), 1e-12) && near(qm::max(-a), -1, 1e-12); });
    return 0;
}
