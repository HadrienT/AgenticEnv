#include "aad.hpp"
#include "chk.hpp"
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <new>
#include <random>
#include <thread>
#include <vector>
using namespace aad;
static std::atomic<long> allocs{0};
void* operator new(std::size_t n) { allocs++; void* p = malloc(n); if (!p) throw std::bad_alloc(); return p; }
void operator delete(void* p) noexcept { free(p); }
void operator delete(void* p, std::size_t) noexcept { free(p); }
static double Phi(double x) { return 0.5 * erfc(-x / std::sqrt(2.0)); }
static double phi(double x) { return std::exp(-0.5 * x * x) / std::sqrt(2 * M_PI); }
template <class T> static T bs(const T& S, const T& K, const T& r, const T& sg, const T& t) {
    using std::log; using std::sqrt; using std::exp;
    T sq = sqrt(t);
    T d1 = (log(S / K) + (r + sg * sg * 0.5) * t) / (sg * sq);
    T d2 = d1 - sg * sq;
    return S * normal_cdf(d1) - K * exp(-(r * t)) * normal_cdf(d2);
}
int main() {
    sec("simple_chain", [] { Tape::active().clear(); Var x(3.0), y(4.0); Var z = x * y + x; Tape::active().propagate(z);
        return near(z.value(), 15, 1e-14) && near(x.adjoint(), 5, 1e-14) && near(y.adjoint(), 3, 1e-14); });
    sec("aliasing", [] { Tape::active().clear(); Var x(3.0); Var a = x * x; Var y = x; y += x; y *= x; Tape::active().propagate(a);
        bool one = near(x.adjoint(), 6, 1e-14);
        Tape::active().propagate(y);
        Var q(2.0); Var r = q; r = r * r; r = r * r;  // q^4
        Tape::active().propagate(r);
        return one && near(q.adjoint(), 32, 1e-12); });
    sec("division_and_compound", [] { Tape::active().clear(); Var x(2.0), y(5.0); Var z = x / y; z -= 1.0 / x; z /= y; Tape::active().propagate(z);
        // z = (x/y - 1/x)/y
        return near(x.adjoint(), (1/5.0 + 1/4.0) / 5, 1e-14) && near(y.adjoint(), (-2/25.0)/5 - (2/5.0 - .5)/25, 1e-14) && near((1.0 + x * 2.0 - 3.0).value(), 2, 1e-15); });
    sec("elementary_functions", [] { Tape::active().clear(); Var x(1.3); Var z = exp(x) * log(x) + sqrt(x) - pow(x, 3.5) + normal_cdf(x) - (-x);
        Tape::active().propagate(z); double h = 1.3;
        double want = std::exp(h) * std::log(h) + std::exp(h) / h + .5 / std::sqrt(h) - 3.5 * std::pow(h, 2.5) + phi(h) + 1;
        return near(x.adjoint(), want, 1e-12) && near(normal_cdf(Var(-8.0)).value(), Phi(-8.0), 1e-22); });
    sec("bs_greeks", [] { Tape::active().clear(); Var S(100), K(95), r(.03), sg(.25), t(1.5); Var p = bs(S, K, r, sg, t); Tape::active().propagate(p);
        double d1 = (std::log(100 / 95.0) + (.03 + .03125) * 1.5) / (.25 * std::sqrt(1.5)), d2 = d1 - .25 * std::sqrt(1.5);
        return near(S.adjoint(), Phi(d1), 1e-12) && near(sg.adjoint(), 100 * phi(d1) * std::sqrt(1.5), 1e-10) && near(r.adjoint(), 95 * 1.5 * std::exp(-.03 * 1.5) * Phi(d2), 1e-10) && near(K.adjoint(), -std::exp(-.045) * Phi(d2), 1e-12); });
    sec("max_kink", [] { Tape::active().clear(); Var a(3.0), b(2.0); Var m = max(a * 2.0, b * 5.0); Tape::active().propagate(m);
        bool o = near(b.adjoint(), 5, 1e-14) && near(a.adjoint(), 0, 1e-14);
        Var c(1.0), d(1.0); Var t = max(c, d); Tape::active().propagate(t); return o && near(c.adjoint(), 1, 1e-14) && near(d.adjoint(), 0, 1e-14); });
    sec("two_outputs", [] { Tape::active().clear(); Var x(2.0), y(3.0); Var f = x * y, g = x + y * y; Tape::active().propagate(f); double a = x.adjoint(); Tape::active().propagate(g);
        return near(a, 3, 1e-14) && near(x.adjoint(), 1, 1e-14) && near(y.adjoint(), 6, 1e-14); });
    sec("rewind_bounded", [] { Tape::active().clear(); Var S(100); auto m = Tape::active().mark(); std::size_t peak = 0;
        for (int i = 0; i < 100000; i++) { Var v = exp(S * 0.01) * S; Tape::active().propagate(v); peak = std::max(peak, Tape::active().size()); Tape::active().rewind(m); }
        return peak < 20 && Tape::active().size() == m.pos && near(S.value(), 100, 0); });
    sec("mc_pathwise_delta", [] { Tape::active().clear(); double S0 = 100, K = 100, r = .02, sg = .2, T = 1; Var S(S0), vol(sg); auto m = Tape::active().mark();
        std::mt19937_64 g(7); std::normal_distribution<double> n; double sum = 0, vsum = 0; int N = 400000;
        for (int i = 0; i < N; i++) { double z = n(g); Var ST = S * exp((r - vol * vol * .5) * T + vol * std::sqrt(T) * z); Var pay = max(ST - K, Var(0.0)) * std::exp(-r * T); Tape::active().propagate(pay); sum += S.adjoint(); vsum += vol.adjoint(); Tape::active().rewind(m); }
        double d1 = (std::log(S0 / K) + (r + .5 * sg * sg) * T) / (sg * std::sqrt(T));
        return near(sum / N, Phi(d1), 0.004) && near(vsum / N, S0 * phi(d1) * std::sqrt(T), 0.12); });
    sec("no_alloc_after_reserve", [] { Tape::active().clear(); Tape::active().reserve(200000); Var x(1.5); long a = allocs; Var y = x; for (int i = 0; i < 40000; i++) y = y * x / x + 1.0; Tape::active().propagate(y); long b = allocs;
        fprintf(stderr, "allocs %ld\n", b - a); return b == a; });
    sec("cost_ratio", [] { Tape::active().clear(); Tape::active().reserve(30000000); volatile double sink = 0; int N = 2000000;
        auto t0 = std::chrono::steady_clock::now();
        Var x(1.0001), y = x; for (int i = 0; i < N; i++) y = y * x + 1.0e-9; sink = y.value();
        auto t1 = std::chrono::steady_clock::now(); Tape::active().propagate(y);
        auto t2 = std::chrono::steady_clock::now();
        double fw = std::chrono::duration<double>(t1 - t0).count(), bw = std::chrono::duration<double>(t2 - t1).count();
        fprintf(stderr, "fw %.3f bw %.3f\n", fw, bw); (void)sink; return bw < 4 * fw && fw < 1.0; });
    sec("thread_local_tapes", [] { std::atomic<bool> ok{true}; std::vector<std::thread> t;
        for (int k = 0; k < 8; k++) t.emplace_back([&, k] { Tape::active().clear(); Var x(1.0 + k); for (int i = 0; i < 2000; i++) { auto m = Tape::active().mark(); Var y = x * x * x; Tape::active().propagate(y); if (std::fabs(x.adjoint() - 3 * (1.0 + k) * (1.0 + k)) > 1e-12) ok = false; Tape::active().rewind(m); } });
        for (auto& th : t) th.join(); return ok.load(); });
    return 0;
}
