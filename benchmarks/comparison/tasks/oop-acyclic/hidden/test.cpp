// Compiled and linked against the prebuilt library: nothing here can reach back into it.
#include "acyclic.hpp"
#include "trades.hpp"
#include "chk.hpp"
#include <memory>
#include <string>
#include <vector>
using namespace trade;
struct Cds : VisitableTrade<Cds> { double spread = 0.01; double protection = 500; std::string type_name() const override { return "CdsXYZ"; } };
struct Risk : VisitorBase, Visitor<Swap>, Visitor<Bond>, Visitor<Cds> { double r = 0; void visit(const Swap& s) override { r += s.notional * s.rate; } void visit(const Bond& b) override { r += b.face * .1; } void visit(const Cds& c) override { r += c.protection * c.spread; } };
struct Ext : NotionalVisitor, Visitor<Cds> { void visit(const Cds& c) override { cds += c.protection; } double cds = 0; using NotionalVisitor::visit; };
struct Once : VisitorBase, Visitor<Cds> { int n = 0; void visit(const Cds&) override { n++; } };
int main() {
    sec("existing_work", [] { NotionalVisitor v; Swap s(100, .02); Bond b(50); const Trade& t1 = s; const Trade& t2 = b; t1.accept(v); t2.accept(v); return near(v.total(), 150, 1e-12) && s.type_name() == "Swap" && b.type_name() == "Bond"; });
    sec("unsupported_throws_with_name", [] { NotionalVisitor v; Cds c; const Trade& t = c; try { t.accept(v); } catch (const UnsupportedTrade& e) { return std::string(e.what()).find("CdsXYZ") != std::string::npos; } return false; });
    sec("new_trade_new_visitor", [] { std::vector<std::unique_ptr<Trade>> ts; ts.push_back(std::make_unique<Swap>(100, .02)); ts.push_back(std::make_unique<Bond>(50)); ts.push_back(std::make_unique<Cds>()); Risk r; for (auto& t : ts) t->accept(r); return near(r.r, 2 + 5 + 5, 1e-12); });
    sec("extend_visitor_by_inheritance", [] { Ext e; Swap s(10, 0); Cds c; Trade& a = s; Trade& b = c; a.accept(e); b.accept(e); return near(e.total(), 10, 1e-12) && near(e.cds, 500, 1e-12); });
    sec("try_accept", [] { NotionalVisitor v; Cds c; Swap s(7, 0); const Trade& a = c; const Trade& b = s; bool x = a.try_accept(v), y = b.try_accept(v); return !x && y && near(v.total(), 7, 1e-12); });
    sec("exactly_one_dispatch", [] { Once o; Cds c; const Trade& t = c; t.accept(o); t.try_accept(o); struct Empty : VisitorBase {} e; bool ok = !t.try_accept(e); return o.n == 2 && ok; });
    return 0;
}
