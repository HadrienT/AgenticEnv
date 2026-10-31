# Comparison results

Tasks run by both agents: 9 of 26.

- On those tasks, AgenticEnv 38/93, Claude Code 92/93.
- AgenticEnv over all 26 tasks: 79/250.

| Task | AgenticEnv | Claude Code |
|---|---|---|
| cpp-aad | 9/12 (455s, finished) | 12/12 (273s, finished) |
| cpp-expr-templates | 0/10 (492s, timeout_or_error) | 10/10 (362s, finished) |
| cpp-threadpool | 1/11 (186s, finished) | 11/11 (1630s, finished) |
| cpp-ub-hunt | 9/11 (187s, finished) | 11/11 (161s, finished) |
| cuda-bug-hunt | 5/9 (105s, finished) | 8/9 (382s, finished) |
| cuda-mc-bs | 0/11 (836s, finished) | 11/11 (305s, finished) |
| cuda-multi-gpu | 6/9 (218s, finished) | 9/9 (464s, finished) |
| mc-asian-cv | 1/11 (341s, finished) | 11/11 (1271s, finished) |
| mc-bug-hunt | 7/9 (185s, finished) | 9/9 (157s, finished) |
| mc-heston-qe | 1/9 (344s, finished) | not run |
| mc-lsm | 3/9 (271s, finished) | not run |
| mc-sobol-bb | 1/10 (159s, finished) | not run |
| model-heston-cf | 1/12 (425s, finished) | not run |
| model-hw-jamshidian | 0/10 (201s, finished) | not run |
| model-implied-vol | 4/9 (688s, finished) | not run |
| model-pde-cn | 1/10 (325s, finished) | not run |
| model-sabr | 2/11 (169s, finished) | not run |
| oop-acyclic | 2/9 (156s, finished) | not run |
| oop-ast-visitors | 5/12 (494s, finished) | not run |
| oop-lazy-observer | 0/12 (714s, timeout_or_error) | not run |
| oop-visitor | 7/12 (190s, finished) | not run |
| qm-add-gap-option | 0/9 (364s, timeout_or_error) | not run |
| qm-fix-barrier | 4/4 (820s, finished) | not run |
| qm-fix-bridge | 3/5 (248s, finished) | not run |
| qm-fix-heston-cos | 1/4 (362s, finished) | not run |
| qm-nav | 6/10 (187s, finished) | not run |
