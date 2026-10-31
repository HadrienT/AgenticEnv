#include "ast.hpp"
#include <stdexcept>
namespace ast {
#define TODO throw std::logic_error("not implemented")
Ptr num(double) { TODO; }
Ptr var(std::string) { TODO; }
Ptr add(Ptr, Ptr) { TODO; }
Ptr sub(Ptr, Ptr) { TODO; }
Ptr mul(Ptr, Ptr) { TODO; }
Ptr neg(Ptr) { TODO; }
Ptr pow_(Ptr, double) { TODO; }
Ptr exp_(Ptr) { TODO; }
Ptr log_(Ptr) { TODO; }
double eval(const Node&, const Env&) { TODO; }
std::string print(const Node&) { TODO; }
std::set<std::string> vars(const Node&) { TODO; }
Ptr clone(const Node&) { TODO; }
Ptr fold(const Node&) { TODO; }
Ptr diff(const Node&, const std::string&) { TODO; }
}
