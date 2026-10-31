#include "ticks.hpp"
#include <cstdio>
int main() { if (ticks::count_ticks(8, 200000) == 1600000) puts("PASS data_race"); else puts("FAIL data_race"); }
