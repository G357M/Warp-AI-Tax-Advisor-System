# Project workflow

## TypeSafe JEV

Use the installed `typesafe-jev` skill by default when implementing or reviewing semantic classification, query routing, document categorization, or bounded rubric-based judgments in this project. Read its `SKILL.md` before the first call. Use JEV as an additional check against source evidence and deterministic tests; resolve disagreements explicitly.

For these tasks, read [docs/TYPESAFE_JEV.md](docs/TYPESAFE_JEV.md) for the project workflow, runtime modes, and evaluation evidence. Start with a small synthetic or anonymized sample and reuse verified results within the task. Keep routine edits, arithmetic, legal conclusions, and release authorization in their existing workflows.

The skill uses this machine's credential environment. Application calls use the backend secret configuration. Report a missing skill/key or unavailable service accurately and continue independent work; never claim a JEV check occurred without an API result.
