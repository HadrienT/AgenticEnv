#pragma once
#include <cstddef>
#include <vector>
namespace qm {
class Vec {
public:
    explicit Vec(std::size_t n, double fill = 0.0) : data_(n, fill) {}
    std::size_t size() const noexcept { return data_.size(); }
    double& operator[](std::size_t i) { return data_[i]; }
    double operator[](std::size_t i) const { return data_[i]; }
private:
    std::vector<double> data_;
};
}  // namespace qm
