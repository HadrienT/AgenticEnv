#include "heston.hpp"
#include <stdexcept>
namespace model {
double heston_call(double, double, double, double, double, const Heston&) { throw std::logic_error("not implemented"); }
double heston_put(double, double, double, double, double, const Heston&) { throw std::logic_error("not implemented"); }
}
