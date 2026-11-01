# Comparison results

Tasks in every run: 9 of 26.

- agenticenv-r1: 38/93 on those tasks.
- agenticenv-r2: 33/93 on those tasks.
- claude-r1: 92/93 on those tasks.
- agenticenv-r1: 79/250 over its 26 tasks.
- agenticenv-r2: 76/250 over its 26 tasks.
- claude-r1: 92/93 over its 9 tasks.

| Task | agenticenv-r1 | agenticenv-r2 | claude-r1 |
|---|---|---|---|
| cpp-aad | 9/12 (455s, finished) | 0/12 (1725s, timeout_or_error) | 12/12 (273s, finished) |
| cpp-expr-templates | 0/10 (492s, timeout_or_error) | 0/10 (256s, finished) | 10/10 (362s, finished) |
| cpp-threadpool | 1/11 (186s, finished) | 1/11 (235s, finished) | 11/11 (1630s, finished) |
| cpp-ub-hunt | 9/11 (187s, finished) | 7/11 (204s, finished) | 11/11 (161s, finished) |
| cuda-bug-hunt | 5/9 (105s, finished) | 6/9 (184s, finished) | 8/9 (382s, finished) |
| cuda-mc-bs | 0/11 (836s, finished) | 1/11 (424s, finished) | 11/11 (305s, finished) |
| cuda-multi-gpu | 6/9 (218s, finished) | 5/9 (305s, finished) | 9/9 (464s, finished) |
| mc-asian-cv | 1/11 (341s, finished) | 5/11 (263s, finished) | 11/11 (1271s, finished) |
| mc-bug-hunt | 7/9 (185s, finished) | 8/9 (292s, finished) | 9/9 (157s, finished) |
| mc-heston-qe | 1/9 (344s, finished) | 3/9 (379s, finished) | not run |
| mc-lsm | 3/9 (271s, finished) | 3/9 (922s, finished) | not run |
| mc-sobol-bb | 1/10 (159s, finished) | 2/10 (206s, finished) | not run |
| model-heston-cf | 1/12 (425s, finished) | 2/12 (513s, finished) | not run |
| model-hw-jamshidian | 0/10 (201s, finished) | 2/10 (260s, finished) | not run |
| model-implied-vol | 4/9 (688s, finished) | 6/9 (329s, finished) | not run |
| model-pde-cn | 1/10 (325s, finished) | 0/10 (283s, finished) | not run |
| model-sabr | 2/11 (169s, finished) | 1/11 (354s, finished) | not run |
| oop-acyclic | 2/9 (156s, finished) | 2/9 (169s, finished) | not run |
| oop-ast-visitors | 5/12 (494s, finished) | 0/12 (929s, timeout_or_error) | not run |
| oop-lazy-observer | 0/12 (714s, timeout_or_error) | 0/12 (516s, finished) | not run |
| oop-visitor | 7/12 (190s, finished) | 10/12 (283s, finished) | not run |
| qm-add-gap-option | 0/9 (364s, timeout_or_error) | 0/9 (939s, finished) | not run |
| qm-fix-barrier | 4/4 (820s, finished) | 4/4 (408s, finished) | not run |
| qm-fix-bridge | 3/5 (248s, finished) | 0/5 (369s, finished) | not run |
| qm-fix-heston-cos | 1/4 (362s, finished) | 1/4 (319s, finished) | not run |
| qm-nav | 6/10 (187s, finished) | 7/10 (258s, finished) | not run |
