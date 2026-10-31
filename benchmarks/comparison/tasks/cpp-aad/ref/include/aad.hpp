#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>
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
    struct Node { std::uint32_t a, b; double da, db; };
    std::vector<Node> nodes; std::vector<double> adj;
    std::size_t rec(std::size_t a, double da, std::size_t b, double db);
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
    std::size_t id;
    double val;
    Var(double v, std::size_t i) : id(i), val(v) {}
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
