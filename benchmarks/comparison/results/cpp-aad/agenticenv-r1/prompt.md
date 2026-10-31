Implement the reverse-mode automatic differentiation library declared in include/aad.hpp: a tape recording the operations on `aad::Var`, in src/aad.cpp. You may add private members to `Var` and `Tape`, but keep every public name and signature; `double` must convert implicitly to `Var` so `x * 2.0` and `1.0 + x` compile.

It must be usable for Monte-Carlo Greeks: tape rewinding keeps memory bounded over a path loop, and the cost of a backward sweep stays a small multiple of the forward evaluation. No external dependency.
