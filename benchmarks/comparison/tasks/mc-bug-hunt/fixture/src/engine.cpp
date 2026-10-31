#include "engine.hpp"
#include <algorithm>
#include <cmath>
#include <mutex>
#include <random>
#include <thread>
#include <vector>
namespace mc {
namespace {
struct Acc {
    double sum = 0, sq = 0;
    std::int64_t n = 0;
    void add(double x) { sum += x; sq += x * x; n++; }
    McResult done(double df) const {
        double mean = sum / double(n);
        double var = (sq - double(n) * mean * mean) / double(n - 1);
        return {df * mean, df * std::sqrt(var / double(n))};
    }
};
double payoff(double s, double k, bool call) { return std::max(call ? s - k : k - s, 0.0); }
}  // namespace

McResult european(const Market& m, double K, double T, bool is_call, std::int64_t paths, std::uint64_t seed, bool antithetic) {
    std::mt19937_64 g(seed);
    std::normal_distribution<double> n;
    double drift = (m.r - m.q + 0.5 * m.sigma * m.sigma) * T, vol = m.sigma * std::sqrt(T);
    Acc a;
    if (antithetic) {
        for (std::int64_t i = 0; i < paths / 2; i++) {
            double z = n(g);
            a.add(payoff(m.S0 * std::exp(drift + vol * z), K, is_call));
            a.add(payoff(m.S0 * std::exp(drift - vol * z), K, is_call));
        }
    } else {
        for (std::int64_t i = 0; i < paths; i++) a.add(payoff(m.S0 * std::exp(drift + vol * n(g)), K, is_call));
    }
    return a.done(std::exp(-(m.r - m.q) * T));
}

McResult asian(const Market& m, double K, double T, int fix, std::int64_t paths, std::uint64_t seed) {
    std::mt19937_64 g(seed);
    std::normal_distribution<double> n;
    double dt = T / fix, drift = (m.r - m.q - 0.5 * m.sigma * m.sigma) * dt, vol = m.sigma * std::sqrt(dt);
    Acc a;
    for (std::int64_t i = 0; i < paths; i++) {
        double x = 0, sum = m.S0;
        for (int k = 0; k < fix; k++) {
            x += drift + vol * n(g);
            sum += m.S0 * std::exp(x);
        }
        a.add(std::max(sum / fix - K, 0.0));
    }
    return a.done(std::exp(-m.r * T));
}

McResult down_out_call(const Market& m, double K, double B, double T, int steps, std::int64_t paths, std::uint64_t seed) {
    std::mt19937_64 g(seed);
    std::normal_distribution<double> n;
    std::uniform_real_distribution<double> u;
    double dt = T / steps, drift = (m.r - m.q - 0.5 * m.sigma * m.sigma) * dt, vol = m.sigma * std::sqrt(dt);
    double lb = std::log(B);
    Acc a;
    for (std::int64_t i = 0; i < paths; i++) {
        double x = std::log(m.S0), weight = 1;
        for (int k = 0; k < steps; k++) {
            double y = x + drift + vol * n(g);
            if (y <= lb) { weight = 0; break; }
            double p = std::exp(-(x - lb) * (y - lb) / (m.sigma * m.sigma * dt));
            weight *= 1 - p;
            x = y;
        }
        a.add(weight * std::max(std::exp(x) - K, 0.0));
    }
    return a.done(std::exp(-m.r * T));
}

McResult digital_mt(const Market& m, double K, double T, std::int64_t paths, std::uint64_t seed, int threads) {
    double drift = (m.r - m.q - 0.5 * m.sigma * m.sigma) * T, vol = m.sigma * std::sqrt(T);
    std::vector<Acc> acc(threads);
    std::vector<std::thread> pool;
    for (int t = 0; t < threads; t++) {
        pool.emplace_back([&, t] {
            std::mt19937_64 g(seed);
            std::normal_distribution<double> n;
            std::int64_t count = paths / threads;
            for (std::int64_t i = 0; i < count; i++) acc[t].add(m.S0 * std::exp(drift + vol * n(g)) > K ? 1.0 : 0.0);
        });
    }
    for (auto& t : pool) t.join();
    Acc all;
    for (auto& a : acc) { all.sum += a.sum; all.sq += a.sq; all.n += a.n; }
    return all.done(std::exp(-m.r * T));
}
}  // namespace mc
