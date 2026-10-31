#pragma once
#include <cstddef>
namespace aad {
class Var;
// One tape per thread: Tape::active() returns this thread's tape.
class Tape {
public:
    struct Mark { std::size_t pos; };
    static Tape& active();
    std::size_t size() const;          // number of recorded nodes
    void reserve(std::size_t nodes);   // after reserve(n), recording up to n nodes allocates nothing
    Mark mark() const;
    void rewind(Mark m);               // drops the nodes recorded after m
    void clear();                      // empties the tape
    void reset_adjoints();             // sets every adjoint to 0
    void propagate(const Var& output); // resets adjoints, seeds output with 1, sweeps back
};
class Var {
public:
    Var(double value = 0.0);           // records a new input node
    double value() const;
    double adjoint() const;            // d(output)/d(this) after Tape::propagate
    Var& operator+=(const Var&);
    Var& operator-=(const Var&);
    Var& operator*=(const Var&);
    Var& operator/=(const Var&);
    // private representation is up to you
};
Var operator+(const Var&, const Var&);
Var operator-(const Var&, const Var&);
Var operator*(const Var&, const Var&);
Var operator/(const Var&, const Var&);
Var operator-(const Var&);
Var exp(const Var&);
Var log(const Var&);
Var sqrt(const Var&);
Var pow(const Var&, double);
Var normal_cdf(const Var&);        // standard normal CDF
Var max(const Var&, const Var&);   // derivative of the larger argument; of the first at a tie
}  // namespace aad
