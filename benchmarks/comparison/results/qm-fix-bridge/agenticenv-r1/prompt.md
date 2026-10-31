Quasi-Monte Carlo prices of path-dependent products look biased: with `mc_sampler = SamplerKind::Sobol` and `mc_brownian_bridge = true`, an arithmetic Asian on a weekly grid disagrees with the same product priced with `mc_brownian_bridge = false`, and the disagreement does not go away with more paths. Prices of plain European options look fine.

Find the root cause in the library and fix it. Keep the fix minimal and do not change any public API.
