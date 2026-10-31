#pragma once
#include <algorithm>
#include <concepts>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <utility>
#include <vector>
#include <functional>
namespace qm {
class Vec;
struct ExprTag {};
template <class E> struct is_vec_expr : std::bool_constant<std::is_base_of_v<ExprTag, E>> {};
template <class E> concept VecExpr = std::is_base_of_v<ExprTag, std::remove_cvref_t<E>>;
// Lvalue Vec is kept by reference, everything else by value.
template <class E> using Hold = std::conditional_t<std::is_lvalue_reference_v<E> && std::is_same_v<std::remove_cvref_t<E>, Vec>, const Vec&, std::remove_cvref_t<E>>;
template <class E> constexpr bool reads_shifted() { return std::remove_cvref_t<E>::shifted; }
class Vec : public ExprTag {
public:
    static constexpr bool shifted = false;
    explicit Vec(std::size_t n, double fill = 0.0) : data_(n, fill) {}
    template <VecExpr E> requires (!std::is_same_v<std::remove_cvref_t<E>, Vec>) Vec(const E& e) : data_(e.size()) { for (std::size_t i = 0; i < data_.size(); i++) data_[i] = e[i]; }
    Vec(const Vec&) = default; Vec(Vec&&) = default;
    Vec& operator=(const Vec& o) { if (size() != o.size()) throw std::invalid_argument("size"); data_ = o.data_; return *this; }
    Vec& operator=(Vec&& o) { if (size() != o.size()) throw std::invalid_argument("size"); data_ = std::move(o.data_); return *this; }
    template <VecExpr E> requires (!std::is_same_v<std::remove_cvref_t<E>, Vec>) Vec& operator=(const E& e) {
        if (e.size() != size()) throw std::invalid_argument("size");
        if constexpr (E::shifted) { std::vector<double> t(size()); for (std::size_t i = 0; i < size(); i++) t[i] = e[i]; data_ = std::move(t); }
        else for (std::size_t i = 0; i < size(); i++) data_[i] = e[i];
        return *this; }
    std::size_t size() const noexcept { return data_.size(); }
    double& operator[](std::size_t i) { return data_[i]; }
    double operator[](std::size_t i) const { return data_[i]; }
private:
    std::vector<double> data_;
};
template <class L, class R, class Op> struct Bin : ExprTag {
    static constexpr bool shifted = std::remove_cvref_t<L>::shifted || std::remove_cvref_t<R>::shifted;
    L l; R r; std::size_t n;
    template <class A, class B> Bin(A&& a, B&& b) : l(std::forward<A>(a)), r(std::forward<B>(b)), n(l.size()) { if (l.size() != r.size()) throw std::invalid_argument("size"); }
    std::size_t size() const { return n; }
    double operator[](std::size_t i) const { return Op{}(l[i], r[i]); }
};
template <class L, class Op> struct Sc : ExprTag {
    static constexpr bool shifted = std::remove_cvref_t<L>::shifted;
    L l; double s; Op op;
    template <class A> Sc(A&& a, double v) : l(std::forward<A>(a)), s(v) {}
    std::size_t size() const { return l.size(); }
    double operator[](std::size_t i) const { return op(l[i], s); }
};
template <class L> struct Shift : ExprTag {
    static constexpr bool shifted = true;
    L l; std::size_t k;
    template <class A> Shift(A&& a, std::size_t v) : l(std::forward<A>(a)), k(v) {}
    std::size_t size() const { return l.size(); }
    double operator[](std::size_t i) const { return l[(i + k) % size()]; }
};
template <VecExpr A, VecExpr B> auto operator+(A&& a, B&& b) { return Bin<Hold<A>, Hold<B>, std::plus<double>>(std::forward<A>(a), std::forward<B>(b)); }
template <VecExpr A, VecExpr B> auto operator-(A&& a, B&& b) { return Bin<Hold<A>, Hold<B>, std::minus<double>>(std::forward<A>(a), std::forward<B>(b)); }
template <VecExpr A> auto operator*(A&& a, double s) { return Sc<Hold<A>, std::multiplies<double>>(std::forward<A>(a), s); }
template <VecExpr A> auto operator*(double s, A&& a) { return Sc<Hold<A>, std::multiplies<double>>(std::forward<A>(a), s); }
template <VecExpr A> auto operator/(A&& a, double s) { return Sc<Hold<A>, std::divides<double>>(std::forward<A>(a), s); }
template <VecExpr A> auto operator-(A&& a) { return Sc<Hold<A>, std::multiplies<double>>(std::forward<A>(a), -1.0); }
template <VecExpr A> auto shift(A&& a, std::size_t k) { return Shift<Hold<A>>(std::forward<A>(a), k); }
template <VecExpr A> double sum(const A& a) { double s = 0; for (std::size_t i = 0; i < a.size(); i++) s += a[i]; return s; }
template <VecExpr A, VecExpr B> double dot(const A& a, const B& b) { if (a.size() != b.size()) throw std::invalid_argument("size"); double s = 0; for (std::size_t i = 0; i < a.size(); i++) s += a[i] * b[i]; return s; }
template <VecExpr A> double max(const A& a) { double m = -std::numeric_limits<double>::infinity(); for (std::size_t i = 0; i < a.size(); i++) m = std::max(m, a[i]); return m; }
}
