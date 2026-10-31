Turn `qm::Vec` in include/vec.hpp into a C++20 expression-template vector library (header-only is fine, a .cpp in src/ is allowed).

Required:
- A concept `qm::VecExpr<E>`: true for Vec and every lazy expression over it; false for double, int, std::string, std::vector<double>.
- Lazy `+`, `-` between two expressions, unary `-`, and `*`, `/` with a double (`e * 2.0`, `2.0 * e`, `e / 2.0`). Operators must take part in overload resolution only for VecExpr, so `Vec + int` and `Vec + std::string` are not valid expressions (usable in a `requires` check, not a hard error).
- Evaluating `a = b + c * 2.0 - d` into an existing Vec `a` of the right size must not allocate heap memory at all, and must make a single pass. Constructing a Vec from an expression allocates exactly once.
- `auto e = (b + c) * 2.0;` must stay valid after the full expression ends: no dangling, even when an operand of the expression is itself a temporary Vec or a temporary expression, as in `auto e = Vec(3, 1.0) + b;` or `auto e = f(b);` where f returns an expression built from its own local temporaries.
- Aliasing must give the right answer: `a = a + b`, `a = b - a`, and `a = shift(a, 1)` where `qm::shift(e, k)` is the lazy view whose element i is `e[(i + k) % n]`. The last one reads elements the assignment has already overwritten if done naively, so it must still equal the shifted original. Plain element-wise expressions must stay allocation-free.
- `.size()` and `operator[]` on every expression. Mismatched sizes throw std::invalid_argument, at the latest when evaluated.
- `qm::sum(e)`, `qm::dot(e1, e2)`, `qm::max(e)` reductions over any expression.

Everything is built with `g++ -std=c++20`, and must pass under AddressSanitizer and UBSan.
