#include "asian.hpp"
#include <stdexcept>
namespace mc {
double geometric_asian_call(double, double, double, double, double, double, int) { throw std::logic_error("not implemented"); }
McResult arithmetic_asian_call(double, double, double, double, double, double, int, std::int64_t, std::uint64_t, bool) { throw std::logic_error("not implemented"); }
}
