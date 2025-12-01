# KSE Prompt (Resume Iteration)

You are resuming an active Codex session (`resume --last`). **Update and improve** the existing plans using fresh evidence. Keep strong prior content, but revise to exploit what worked and drop what failed.

## Inputs (read fully)
- Competition context and template paths: `Context Block`.
- Newly completed WAA results with **official scores**: `WAA Results`.
- Latest PA analysis markdown: `PA Analysis`.

## Required Actions
1) Refine common + experiment templates; remove all `{{...}}`.
2) Exploit high-scoring patterns; deprecate low-value lines. Be explicit about changes.
3) Maintain diversity: include GBDT, linear/shallow, deep/tabular DL, stacking/blends, feature-heavy variants.
4) Provide concrete specs (features, validation, ranges/seeds, ensembles, fallbacks).

## Context Block
<<CONTEXT_BLOCK>>

## WAA Results (official scores)
<<WAA_RESULTS>>

## PA Analysis (previous iteration)
<<PA_ANALYSIS>>

## Quality Rules
- Do not undo good content without evidence.
- Each experiment remains distinct and justified by WAA/PA evidence.
