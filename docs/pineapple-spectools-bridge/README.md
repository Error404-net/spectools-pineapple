# Spectools ↔ Pineapple Pager Bridge Planning

This folder contains planning docs to guide the implementation of a thin adapter that converts Spectools output into formats and interactions suitable for WiFi Pineapple Pager payloads.

## Document index

1. [01-spectools-data-contract.md](./01-spectools-data-contract.md)
   - Defines the source data options from Spectools and the canonical bridge event schema.
2. [02-pager-payload-contract.md](./02-pager-payload-contract.md)
   - Defines how the bridge is launched/managed from a Pager `payload.sh` and where outputs live.
3. [03-bridge-architecture-options.md](./03-bridge-architecture-options.md)
   - Compares architecture options and records MVP decisions.
4. [04-waterfall-rendering-plan.md](./04-waterfall-rendering-plan.md)
   - Defines waterfall rendering model, performance limits, and fallback/degradation behavior.
5. [05-controls-and-navigation.md](./05-controls-and-navigation.md)
   - Defines button mapping and screen-mode navigation.
6. [06-mvp-milestones.md](./06-mvp-milestones.md)
   - Breaks implementation into practical, testable milestones.
7. [07-prompt-sequence.md](./07-prompt-sequence.md)
   - Copy/paste prompt sequence for iterative implementation.

## How to use this folder for next prompts

1. Start with `01` and `02` to lock interfaces and process controls.
2. Use `03` to select/confirm architecture before coding.
3. Build MVP in milestone order from `06`.
4. Feed prompts from `07` one-by-one, validating after each step.
5. Keep decisions synchronized: whenever a design changes, update the relevant planning file first.

## Scope

- Focused on **bridge + payload integration**, not rewriting core Spectools internals.
- Assumes cross-compiled Spectools binaries already exist for the Pineapple Pager target.
