# 03 - Bridge Architecture Options

## Objective

Choose the fastest safe path to MVP while preserving a path to more robust ingestion.

## Option matrix

| Option | Description | Build Speed | Robustness | Runtime Cost | Compatibility | Notes |
|---|---|---:|---:|---:|---:|---|
| A | Parse `spectool_raw` text output | 5/5 | 2/5 | 5/5 | 5/5 | Fastest MVP; fragile if output format shifts |
| B | Decode `spectool_net` binary frames | 3/5 | 5/5 | 4/5 | 4/5 | Better structure; requires frame parser |
| C | Add native JSON output mode in Spectools C | 2/5 | 5/5 | 5/5 | 3/5 | Best long term; touches legacy code |

## Option details

### Option A - `spectool_raw` parser

Pros:

- Reuses existing binaries without modification.
- Very low lift for first working demo.

Cons:

- Depends on line-format assumptions.
- Harder to encode richer metadata without heuristics.

### Option B - `spectool_net` decoder

Pros:

- Structured protocol includes device and sweep framing.
- Cleaner mapping to typed bridge events.

Cons:

- More implementation effort in parser and connection handling.

### Option C - native JSON mode in C

Pros:

- Most direct and efficient output for bridge/UI.
- Eliminates brittle text parsing.

Cons:

- Requires changes to legacy C toolchain and rebuild process.

## Recommended decision

### MVP

- **Select Option A** for immediate usability and prompt-driven iteration.

### Immediate fallback

- If text parsing proves unstable, move to **Option B**.

### Deferred

- Track **Option C** as post-MVP hardening once UX is validated.

## Non-goals (for MVP)

- Reworking GTK components.
- Full historical RF analytics backend.
- Multi-user remote dashboards.
