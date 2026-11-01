This small library in src/ticks.cpp works "most of the time" but is full of undefined behaviour. The header comments state what each function must do. Fix every memory-safety, undefined-behaviour and data-race bug so the whole library is clean under ASan, UBSan and TSan.

You can change a return type or a signature only if keeping it makes correctness impossible; if you do, update the header and keep the function names. Do not disable any sanitizer or add suppressions.
