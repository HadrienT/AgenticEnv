#include "sabr.hpp"
#include <stdexcept>
namespace model {
double sabr_vol(double, double, double, const SabrParams&) { throw std::logic_error("not implemented"); }
SabrParams sabr_calibrate(double, double, double, const std::vector<double>&, const std::vector<double>&) { throw std::logic_error("not implemented"); }
}
