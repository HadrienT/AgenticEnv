#include "lsm.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <random>
#include <vector>
namespace mc {
McResult american_put_lsm(double S0, double K, double r, double sg, double T, int st, std::int64_t N, std::uint64_t seed) {
    std::mt19937_64 g(seed); std::normal_distribution<double> nd; std::int64_t half = N / 2; N = half * 2; double dt = T / st, df = std::exp(-r * dt), dr = (r - .5 * sg * sg) * dt, vl = sg * std::sqrt(dt);
    std::vector<float> Z(size_t(half) * st); for (auto& z : Z) z = float(nd(g));
    auto gaussian = [&](int k, std::int64_t i) { return i < half ? double(Z[size_t(i) * st + k]) : -double(Z[size_t(i - half) * st + k]); };
    std::vector<double> X(N, 0.0); for (int k = 0; k < st; k++) for (std::int64_t i = 0; i < N; i++) X[i] += dr + vl * gaussian(k, i);
    std::vector<double> cf(N); for (std::int64_t i = 0; i < N; i++) cf[i] = std::max(1 - S0 / K * std::exp(X[i]), 0.0);
    for (int k = st - 1; k >= 1; k--) {
        for (std::int64_t i = 0; i < N; i++) { X[i] -= dr + vl * gaussian(k, i); cf[i] *= df; }
        double A[4][5] = {}; std::int64_t cnt = 0;
        for (std::int64_t i = 0; i < N; i++) { double x = S0 / K * std::exp(X[i]); if (x < 1) { cnt++; double b[4] = {1, x, x * x, x * x * x}; for (int a = 0; a < 4; a++) { for (int c = 0; c < 4; c++) A[a][c] += b[a] * b[c]; A[a][4] += b[a] * cf[i]; } } }
        if (cnt < 8) continue;
        for (int c = 0; c < 4; c++) { int p = c; for (int a = c; a < 4; a++) if (std::fabs(A[a][c]) > std::fabs(A[p][c])) p = a; std::swap(A[c], A[p]); for (int a = 0; a < 4; a++) if (a != c) { double f = A[a][c] / A[c][c]; for (int e = c; e < 5; e++) A[a][e] -= f * A[c][e]; } }
        double b[4]; for (int c = 0; c < 4; c++) b[c] = A[c][4] / A[c][c];
        for (std::int64_t i = 0; i < N; i++) { double x = S0 / K * std::exp(X[i]); if (x < 1 && 1 - x > b[0] + x * (b[1] + x * (b[2] + x * b[3]))) cf[i] = 1 - x; }
    }
    double s = 0, v = 0; for (std::int64_t i = 0; i < half; i++) { double p = .5 * (cf[i] + cf[i + half]) * K * df; s += p; v += p * p; }
    double m = s / half, var = (v - half * m * m) / (half - 1); double price = std::max(m, std::max(K - S0, 0.0));
    return {price, std::sqrt(std::max(var, 0.0) / half)};
}
}
