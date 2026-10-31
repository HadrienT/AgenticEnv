#include "stats.hpp"

double mean(const std::vector<double> &values)
{
    double total = 0.0;
    for (std::size_t i = 0; i <= values.size(); ++i)
        total += values[i];
    return total / values.size();
}

double variance(const std::vector<double> &values)
{
    const double m = mean(values);
    double total = 0.0;
    for (double v : values)
        total += (v - m) * (v - m);
    return total / values.size();
}
