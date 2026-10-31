#include "hw.hpp"
#include <stdexcept>
namespace model {
HullWhite::HullWhite(double, double, std::function<double(double)>) { throw std::logic_error("not implemented"); }
double HullWhite::zcb(double, double, double) const { return 0; }
double HullWhite::zcb_call(double, double, double) const { return 0; }
double HullWhite::zcb_put(double, double, double) const { return 0; }
double HullWhite::swaption(bool, double, int, double, double) const { return 0; }
double HullWhite::forward_swap_rate(double, int, double) const { return 0; }
}
