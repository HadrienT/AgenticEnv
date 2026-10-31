#pragma once
#include <cstdint>
#include <vector>
#include "sobol_data.hpp"
namespace mc {
// Sobol sequence in Gray-code order, up to 32 dimensions, 32-bit direction integers.
// Dimension 1 is van der Corput; dimensions 2.. come from SOBOL_DATA.
// Point index 0 is the origin. next() returns coordinates x_k = bits / 2^32 in [0, 1).
class Sobol {
public:
    explicit Sobol(int dim);
    void next(double* out);
};
// Maps n iid standard normals to the path W(t_i), t_i = i*T/n, by Brownian bridge
// construction: z[0] fixes W(T), z[1] the midpoint, and so on, so the leading z carry
// most of the variance. n is a power of two. w has n entries.
void brownian_bridge(const double* z, int n, double T, double* w);
struct McResult { double price; double std_error; };
// Arithmetic Asian call, fixings t_i = i*T/n, n a power of two. Randomised QMC: `replicas`
// independent digital shifts of a Sobol set of `points` points. price is their mean,
// std_error their sample standard error. use_bridge selects Brownian-bridge path construction,
// otherwise dimensions are assigned to time steps in order (forward construction).
McResult asian_rqmc(double S0, double K, double r, double sigma, double T, int n,
                    int points, int replicas, std::uint64_t seed, bool use_bridge);
}  // namespace mc
