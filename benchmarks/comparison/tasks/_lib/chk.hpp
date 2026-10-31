// Each section runs in its own process: a crash or a hang costs one check, not the file.
#pragma once
#include <sys/wait.h>
#include <unistd.h>
#include <cmath>
#include <cstdio>
#include <algorithm>
#include <exception>
#include <initializer_list>
#include <limits>
#include <stdexcept>
#include <vector>
template <class F>
void sec(const char* name, F f, int timeout_s = 120) {
    fflush(stdout); fflush(stderr);
    pid_t pid = fork();
    if (pid == 0) {
        alarm(timeout_s);
        bool ok = false;
        try { ok = f(); }
        catch (const std::exception& e) { fprintf(stderr, "[%s] exception: %s\n", name, e.what()); }
        catch (...) { fprintf(stderr, "[%s] exception\n", name); }
        fflush(stdout); fflush(stderr);
        _exit(ok ? 0 : 1);
    }
    int st = 0;
    waitpid(pid, &st, 0);
    bool ok = WIFEXITED(st) && WEXITSTATUS(st) == 0;
    printf("%s %s\n", ok ? "PASS" : "FAIL", name);
    fflush(stdout);
}
inline bool near(double a, double b, double tol) {
    bool ok = std::fabs(a - b) <= tol;
    if (!ok) fprintf(stderr, "  got %.10g want %.10g tol %.3g\n", a, b, tol);
    return ok;
}
