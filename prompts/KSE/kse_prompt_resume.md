# KSE Prompt (Resume Iteration)

You are resuming the Knowledge Strategy Engine with new evidence from completed experiments. Your task is to **evolve the heuristic strategy** based on what worked and what failed, while maintaining diversity.

---

## YOUR MISSION: Strategic Evolution

### Analyze Before Acting
Before generating new hypotheses:
1. **Rank all experiments by official score**
2. **Identify the top 2-3 performing strategies** and extract their key operators
3. **Identify complete failures** and understand root causes
4. **Calculate improvement rate**: Are scores improving, plateauing, or declining?
5. **Check diversity**: Were previous hypotheses truly different?

### Evolution, Not Revolution
- Keep what works—don't abandon successful patterns without evidence
- Fix what failed—understand root causes before retrying similar approaches
- Fill gaps—what hasn't been tried that should be?

---

## PHASE 1: Previous Results Analysis

### Deep Dive on Results
For each completed experiment:
- What was the official score? (primary metric)
- What was the local score? (stability indicator)
- How stable were results across seeds or restarts?
- What unique operators or heuristics did it use?
- Why did it succeed or fail?

### PA Recommendations Review
Extract from PA analysis:
- **MUST DO**: Actions PA marked as non-negotiable
- **MUST NOT DO**: Approaches PA marked as failures to avoid
- **QUESTIONS TO ANSWER**: Hypotheses PA wants tested

### Trajectory Assessment
Calculate:
- **Score improvement**: Best score this iteration vs. previous best
- **Improvement rate**: Trend over iterations
- **Gap to ceiling**: Distance from known benchmarks/winning scores

---

## PHASE 2: Strategy Evolution Rules

### Adapt Resource Allocation Based on Trajectory

**If IMPROVING (>1% gain per iteration):**
- **60% Exploitation**: Refine winning approaches with targeted improvements
- **30% Exploration**: Try promising untested approaches
- **10% Moonshot**: One high-risk/high-reward experiment

**If PLATEAUING (<1% gain for 2+ iterations):**
- **30% Exploitation**: Only the very best performers
- **50% Exploration**: Significantly different approaches
- **20% Moonshot**: Novel techniques from recent research

**If DECLINING (scores getting worse):**
- **20% Exploitation**: Stabilize best known approach
- **40% Diagnostic**: Experiments to understand what broke
- **40% Reset**: Return to simpler baselines and rebuild

### Depth Escalation Rule (MANDATORY)
- Always include at least one **deep** run for the top-performing family (2-3x the probe budget)
- Reuse the best parameter sets; change only a small subset per iteration
- If official scores are missing, base decisions on local score + validity rate

### Kill and Replace Protocol

**Remove approaches that:**
- Failed twice without improvement
- Have fundamental flaws identified by PA
- Are too similar to better-performing alternatives

**Replace with:**
- Genuinely new heuristic families
- Combinations of successful operators from top experiments
- PA high-priority recommendations

**Document:**
- What was killed and why
- What replaced it and why it's expected to perform better

---

## PHASE 3: Research Update (MANDATORY)

### Web Search for Fresh Ideas
Use web search to find:
- New heuristics that might address observed weaknesses
- Community solutions to similar optimization problems
- Updated benchmarks or methods published recently
- Winning approaches from similar competitions

### Apply Research to Strategy
- Which findings apply to high-priority PA recommendations?
- What new techniques could break the plateau (if plateauing)?
- What fundamentally different approaches haven't been tried?

---

## PHASE 4: Hypothesis Generation with Evidence

### For Each Hypothesis, Document:

**Builds on:**
- Which previous experiment(s) this extends (cite exp_ids)
- What specific elements are being kept and why

**Addresses:**
- Which PA insight or recommendation this targets
- What unresolved question this helps answer

**Differentiates by:**
- How this is fundamentally different from other hypotheses this round
- What unique operator set or search strategy it uses

**Budget and inheritance:**
- Budget tier (probe/deep) and expected runtime
- Which parameters are inherited vs changed

**Research source:**
- What web search finding or discussion insight supports this
- Why this approach is expected to work

---

## Inputs (Read Fully)

### Context Block
Contains: Competition context, data paths, templates
<<CONTEXT_BLOCK>>

### WAA Results (Official Scores)
Contains: Completed experiment results with official/public leaderboard scores
<<WAA_RESULTS>>

### PA Analysis (Previous Iteration)
Contains: Performance analysis with success/failure patterns and recommendations
<<PA_ANALYSIS>>

---

## Required Diversity (Maintain Across Iterations)

Even in later iterations, maintain coverage:
1. **Greedy/Constructive Baseline**: At least one simple baseline
2. **Local Search**: At least one neighborhood-based approach
3. **Metaheuristic**: At least one SA/Tabu/ILS/VNS
4. **Population-Based**: At least one GA/ES
5. **Hybrid or Constraint/Exact**: At least one CP-SAT/ILP or hybrid approach

**Note**: You may retire approaches in categories that consistently fail, but document the decision and have coverage in other categories.

---

## Deliverables

### 1. Evolution Summary (NEW)
Document at the start of common template:
- What changed from previous iteration and why
- Which approaches were killed and why
- Which new approaches were added and why
- Current trajectory assessment (improving/plateauing/declining)
- Which parameters/budgets were carried over from top performers

### 2. Updated Common Template
- Refine based on learnings
- Update research findings section with new discoveries
- Adjust evaluation strategy if evidence supports changes

### 3. Updated Experiment Templates
For each hypothesis:
- Clear evidence-based justification
- Explicit link to PA recommendations
- Differentiation statement
- Expected improvement with rationale

### 4. Updated Diversity Matrix
Show how diversity is maintained despite strategic evolution.

---

## Quality Rules

### Evidence-Based Changes
- **DO NOT** undo good content without evidence
- **DO NOT** abandon successful patterns arbitrarily
- **DO** cite specific experiment results for every major decision
- **DO** reference PA analysis for recommendations

### Hypothesis Quality
- Each experiment remains distinct (verified via diversity matrix)
- Each experiment is justified by WAA/PA evidence
- No near-duplicates of previous iterations
- No placeholders (`{{...}}`) remain
- Each experiment enforces official constraint validation (no proxy-only geometry)
 - Depth is allocated to proven families while diversity coverage is maintained

### Strategic Coherence
- Evolution should be logical progression from previous iteration
- Changes should address identified weaknesses
- New approaches should fill gaps, not repeat mistakes

---

## Anti-Patterns to Avoid

- **Overreaction**: Abandoning an entire approach category due to one failure
- **Underreaction**: Repeating failed approaches without meaningful changes
- **Tunnel vision**: Over-focusing on one approach at expense of diversity
- **Churn**: Changing everything each iteration without learning
- **Ignoring PA**: Not incorporating PA's prioritized recommendations
