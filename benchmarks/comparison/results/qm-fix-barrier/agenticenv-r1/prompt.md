A desk reports that continuously monitored barrier options priced by Monte Carlo with the Brownian-bridge correction are too expensive. For a down-and-out call with spot 100, strike 100, barrier 90, rate 5%, dividend 2%, vol 20%, 1 year, the Monte Carlo engine in the pricing registry (`InstrumentKind::EquityBarrierOption`, `EngineKind::MonteCarlo`, brownian_bridge = true) gives a price well above the Rubinstein-Reiner closed form, and the gap does not close as paths grow.

Find the root cause in the library and fix it. Keep the fix minimal and do not change any public API.
