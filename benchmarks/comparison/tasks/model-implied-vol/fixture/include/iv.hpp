#pragma once
namespace model {
double bs_price(double S, double K, double r, double q, double sigma, double T, bool is_call);
// Black-Scholes implied volatility. Returns NaN when no volatility reproduces `price`,
// which covers prices at or below the discounted intrinsic value, prices at or above the
// no-arbitrage upper bound, and non-finite or non-positive inputs. Never throws.
double implied_vol(double price, double S, double K, double r, double q, double T, bool is_call);
}  // namespace model
