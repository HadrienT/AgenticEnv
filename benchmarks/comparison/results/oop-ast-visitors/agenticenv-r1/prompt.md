Implement the expression tree of include/ast.hpp in C++20. Keep the free functions exactly as declared. Design the `Node` hierarchy and a Visitor for it: every operation (`eval`, `print`, `vars`, `clone`, `fold`, `diff`) is a separate visitor class, in src/. Nodes know nothing about these operations apart from `accept`. A transforming visitor returns a new tree and must never mutate its input.

`print` rules: operators ` + `, ` - `, ` * ` with single spaces, `^` with no spaces, `-x` for neg, `exp(x)`, `log(x)`. Numbers print in `%g` format. Parentheses appear only when required by precedence (`^` above unary minus above `*` above `+`/`-`), with left associativity: `(a + b) * c`, `a + b * c`, `a - (b - c)`, `a - b - c`, `a * (b + c)`, `(a * b)^2`, `-(a + b)`, `-a * b`, `(-a)^2`. A negative number literal counts as a unary minus for this purpose.

`fold`: evaluates all constant sub-trees, then simplifies `x + 0`, `0 + x`, `x - 0`, `0 - x` (to `-x`), `x * 1`, `1 * x`, `x * 0`, `0 * x`, `x^1`, `x^0`, `-(-x)` everywhere, in a bottom-up pass to a fixed point.

`diff`: symbolic derivative, valid for every node type. The result need not be simplified, but `print(fold(diff(n, x)))` must be correct.

The tree must be safe at any depth: a tree built by chaining a million `add(std::move(t), num(1))` must be destroyed without blowing the stack. Only destruction has this requirement, and `eval` and the rest may recurse.
