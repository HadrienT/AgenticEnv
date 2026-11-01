This Monte Carlo engine in src/engine.cpp gives wrong answers. Prices disagree with closed-form values, and some standard errors cannot be trusted. Several independent bugs are hiding in it. Find and fix all of them, using the comments in include/engine.hpp as the spec.

Keep the public API in the header unchanged.
