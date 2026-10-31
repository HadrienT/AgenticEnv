#pragma once
#include <vector>
namespace model {
struct SabrParams { double alpha, beta, rho, nu; };
// Hagan et al. (2002) lognormal implied volatility expansion, eq. (2.17a), with its
// time correction; K = F uses the at-the-money form (2.18).
double sabr_vol(double F, double K, double T, const SabrParams& p);
// Least-squares fit of alpha, rho, nu to (strike, vol) market quotes, beta held fixed.
// Throws std::invalid_argument for fewer than 3 quotes, mismatched sizes, non-positive
// F, strikes, vols or T. At the result, |rho| < 1, alpha > 0 and nu >= 0 always hold.
SabrParams sabr_calibrate(double F, double T, double beta, const std::vector<double>& strikes, const std::vector<double>& vols);
}  // namespace model
