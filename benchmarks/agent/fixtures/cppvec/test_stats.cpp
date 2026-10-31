#include "stats.hpp"
#include <cassert>
#include <cmath>

int main()
{
    assert(std::abs(mean({1.0, 2.0, 3.0}) - 2.0) < 1e-12);
    assert(std::abs(variance({1.0, 2.0, 3.0}) - 1.0) < 1e-12);
    return 0;
}
