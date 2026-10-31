#pragma once
#include <map>
#include <memory>
#include <set>
#include <string>
namespace ast {
class Node;
using Ptr = std::unique_ptr<Node>;
using Env = std::map<std::string, double>;

// Node hierarchy and its visitor are yours to design: see the task description.
class Node {
public:
    virtual ~Node() = default;
};

Ptr num(double v);
Ptr var(std::string name);
Ptr add(Ptr a, Ptr b);
Ptr sub(Ptr a, Ptr b);
Ptr mul(Ptr a, Ptr b);
Ptr neg(Ptr a);
Ptr pow_(Ptr base, double exponent);
Ptr exp_(Ptr a);
Ptr log_(Ptr a);

double eval(const Node& n, const Env& env);   // std::out_of_range on an unknown variable
std::string print(const Node& n);
std::set<std::string> vars(const Node& n);
Ptr clone(const Node& n);
Ptr fold(const Node& n);                      // new tree, input untouched
Ptr diff(const Node& n, const std::string& x);// new tree, input untouched
}  // namespace ast
