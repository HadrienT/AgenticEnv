#include "qmc.hpp"
#include <stdexcept>
namespace mc {
Sobol::Sobol(int) { throw std::logic_error("not implemented"); }
void Sobol::next(double*) { throw std::logic_error("not implemented"); }
void brownian_bridge(const double*, int, double, double*) { throw std::logic_error("not implemented"); }
McResult asian_rqmc(double, double, double, double, double, int, int, int, std::uint64_t, bool) { throw std::logic_error("not implemented"); }
}
