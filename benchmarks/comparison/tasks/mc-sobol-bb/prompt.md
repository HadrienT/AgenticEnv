Implement include/qmc.hpp in src/qmc.cpp, in C++20 with the standard library only: a Sobol generator, a Brownian bridge and a randomised QMC Asian pricer. The header comments are the spec. The direction-number data is in include/sobol_data.hpp. You may add private members to `Sobol`.

The normal inverse used to map uniforms must be accurate in the tails and safe when a shifted coordinate is exactly 0.
