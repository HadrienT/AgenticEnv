#include "ast.hpp"
#include <cstdio>
using namespace ast;
int main() { auto n = add(mul(var("a"), pow_(var("b"), 3)), exp_(neg(log_(var("a"))))); auto d = diff(*n, "a"); auto f = fold(*d); auto c = clone(*f); auto g = fold(*diff(*c, "b")); printf("%s\n", print(*g).c_str()); auto t = num(0); for (int i = 0; i < 300000; i++) t = add(std::move(t), num(1)); puts("PASS no_leaks_asan"); }
