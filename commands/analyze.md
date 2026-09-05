---
description: Scan the repo deterministically and propose gates, privacy rule and routing (writes docs/council-analysis.md)
---

Call `council_analyze`. Show the Markdown as-is, then propose the concrete `council.json` edits
(gates, never_share additions) as a diff and ask the user whether to apply them. Do not apply
without a yes. If the repo is `legacy` (no tests, medium+ size), recommend the first wave be
characterisation tests before any refactor card.
