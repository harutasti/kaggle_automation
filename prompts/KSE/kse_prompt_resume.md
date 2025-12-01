# KSE Prompt (Resume Iteration)

You are continuing an active Codex session (`resume --last`). Update the experiment plans based on new evidence from completed WAAs and the latest PA analysis. Keep prior good content, but improve it using the new information below.

## Required Inputs (read carefully)
- Competition context, rules, metric, data sources, and template paths are provided below.
- Newly completed WAA experiments with **official scores** are embedded in `WAA Results`; incorporate their learnings.
- The most recent PA analysis markdown is embedded in `PA Analysis`; honor its insights and recommendations.

## Actions
1) Refine the common template and all experiment templates; remove every `{{...}}` placeholder.
2) Adjust strategies to exploit high-scoring patterns and drop failing ones (per WAA Results + PA Analysis).
3) Keep Markdown well structured; do not create extra files.

## Context Block
<<CONTEXT_BLOCK>>

## WAA Results (official scores)
<<WAA_RESULTS>>

## PA Analysis (previous iteration)
<<PA_ANALYSIS>>

## Quality Rules
- Do not overwrite validated good content without reason; only improve where evidence suggests.
- Maintain diversity across experiments (model families, feature ideas, validation choices).
- Explicitly incorporate findings from WAA Results and PA Analysis.
