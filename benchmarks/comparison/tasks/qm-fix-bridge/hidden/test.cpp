#include "quantModeling/utils/brownian_bridge.hpp"
#include "quantModeling/core/types.hpp"
#include "chk.hpp"
#include <random>
using namespace quantModeling;
static bool cov(std::vector<Time> t) { BrownianBridge b(t); size_t n = t.size(); std::mt19937_64 g(3); std::normal_distribution<double> nd; std::vector<Real> z(n), w(n); std::vector<double> c(n * n, 0.0); int N = 2000000; for (int p = 0; p < N; p++) { for (auto& x : z) x = nd(g); b.transform(z, w); for (size_t i = 0; i < n; i++) for (size_t j = 0; j < n; j++) c[i * n + j] += w[i] * w[j]; } for (size_t i = 0; i < n; i++) for (size_t j = 0; j < n; j++) if (fabs(c[i * n + j] / N - std::min(t[i], t[j])) > .02) { fprintf(stderr, "got cov %zu %zu %.4f want %.4f\n", i, j, c[i * n + j] / N, std::min(t[i], t[j])); return false; } return true; }
int main() {
    sec("path_covariance_uneven_grid", [] { return cov({.05, .1, .3, .35, .8, 1.0, 1.7}); }, 100);
    sec("path_covariance_even_grid", [] { return cov({.25, .5, .75, 1, 1.25, 1.5, 1.75, 2}); }, 100);
    sec("bridge_leaves_first_variate", [] { std::vector<Time> t{.5, 1, 1.5, 2}; BrownianBridge b(t); std::vector<Real> z{1.5, 0, 0, 0}, w(4); b.transform(z, w); return near(w[3], 1.5 * sqrt(2.0), 1e-12) && near(w[1], .75 * sqrt(2.0), 1e-12); });
    return 0;
}
