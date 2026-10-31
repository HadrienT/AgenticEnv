#include "heston.hpp"
#include <stdexcept>
namespace mc {
McResult heston_call_mc(const HestonParams&, double, double, int, std::int64_t, std::uint64_t) { throw std::logic_error("not implemented"); }
McResult heston_forward_mc(const HestonParams&, double, int, std::int64_t, std::uint64_t) { throw std::logic_error("not implemented"); }
}
