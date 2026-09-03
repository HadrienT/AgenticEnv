<!-- page:1 -->
# Model Overview

This paper presents a small volatility model used for illustration purposes only.

## Derivation

We start from the returns $r_i$ and derive the estimator below.

$$
\hat{\sigma} = \sqrt{\frac{1}{n-1} \sum_{i=1}^{n} (r_i - \bar{r})^2} \tag{2}
$$

This estimator is an unbiased sample standard deviation.

<!-- page:2 -->
## Summary Table

Table: Model parameters used in the simulation.

| Parameter | Value |
| --- | --- |
| n | 252 |
| alpha | 0.05 |

These parameters were chosen to match a one-year trading horizon.
