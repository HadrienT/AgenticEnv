---
name: quant-conventions
description: This skill should be used when the user asks to edit, review, or write code that touches pricing models, calibration, or numerical methods, or mentions "units", "convention", "tolerance", or "quant-modeling".
triggers:
- units
- convention
- tolerance
- quant-modeling
- numerical method
---

# Quant Conventions

This repository encodes financial and numerical conventions that must never
be silently reinterpreted by an agent.

## Core Instructions

1. Before changing a function that takes a rate, volatility, price, or time
   parameter, check its existing docstring/comments and any nearby test for
   the unit convention in use (e.g. annualized vs. per-period, percent vs.
   decimal). Do not assume a convention from a variable name alone.
2. Preserve existing tolerances (e.g. `1e-8` style constants) unless the task
   explicitly asks to change one — do not "round" a tolerance to make a test
   pass.
3. Never compute a numerical result (price, greek, calibrated parameter)
   yourself — always run the project's own build/test/bench tool and report
   its actual output. See the `rag-citation` skill for the same rule applied
   to formulas.
4. When in doubt about a convention, search the knowledge base (`kb.search`)
   before guessing.

## Common Patterns

- Adding a new pricing function: mirror the unit convention of the closest
  existing function in the same header/module.
- Changing a calibration tolerance: requires an explicit task instruction and
  a note in the commit message explaining why the old tolerance was wrong.
