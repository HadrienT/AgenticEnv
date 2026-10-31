#pragma once
#include <functional>
namespace model {
// One-factor Hull-White fitted to the initial discount curve P(0, t): dr = (theta(t) - a r) dt + sigma dW.
class HullWhite {
public:
    HullWhite(double a, double sigma, std::function<double(double)> discount);
    // P(t, T) given the short rate r(t) = r_t. instantaneous_forward(t) is needed by the formula:
    // differentiate the curve numerically with a central difference.
    double zcb(double t, double T, double r_t) const;
    // European options expiring at T on the zero-coupon bond maturing at S, strike K.
    double zcb_call(double K, double T, double S) const;
    double zcb_put(double K, double T, double S) const;
    // European swaption, expiry T0, fixed leg paying K*tau at T0 + i*tau, i = 1..n, by
    // Jamshidian's decomposition. A payer swaption pays fixed. Unit notional, single curve.
    double swaption(bool payer, double T0, int n, double tau, double K) const;
    // The par rate of that swap as seen today.
    double forward_swap_rate(double T0, int n, double tau) const;
};
}  // namespace model
