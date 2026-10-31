#include "aad.hpp"
#include <stdexcept>
namespace aad {
static void todo() { throw std::logic_error("not implemented"); }
Tape& Tape::active() { todo(); static Tape t; return t; }
std::size_t Tape::size() const { todo(); return 0; }
void Tape::reserve(std::size_t) { todo(); }
Tape::Mark Tape::mark() const { todo(); return {0}; }
void Tape::rewind(Mark) { todo(); }
void Tape::clear() { todo(); }
void Tape::reset_adjoints() { todo(); }
void Tape::propagate(const Var&) { todo(); }
Var::Var(double) { todo(); }
double Var::value() const { todo(); return 0; }
double Var::adjoint() const { todo(); return 0; }
Var& Var::operator+=(const Var&) { todo(); return *this; }
Var& Var::operator-=(const Var&) { todo(); return *this; }
Var& Var::operator*=(const Var&) { todo(); return *this; }
Var& Var::operator/=(const Var&) { todo(); return *this; }
Var operator+(const Var&, const Var&) { todo(); return {}; }
Var operator-(const Var&, const Var&) { todo(); return {}; }
Var operator*(const Var&, const Var&) { todo(); return {}; }
Var operator/(const Var&, const Var&) { todo(); return {}; }
Var operator-(const Var&) { todo(); return {}; }
Var exp(const Var&) { todo(); return {}; }
Var log(const Var&) { todo(); return {}; }
Var sqrt(const Var&) { todo(); return {}; }
Var pow(const Var&, double) { todo(); return {}; }
Var normal_cdf(const Var&) { todo(); return {}; }
Var max(const Var&, const Var&) { todo(); return {}; }
}
