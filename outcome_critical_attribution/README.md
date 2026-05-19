# Outcome-Critical Trajectory Attribution

A general research prototype for learning which parts of an agent's trajectory
are *causally necessary* for success. Domain-agnostic: coding, browser,
research, workflow, and data-analysis agents all flow through the same
pipeline.

## The core idea

> First identify the minimal set of final outcome atoms required for success.
> Then trace which trajectory atoms produced those outcome atoms. Then train a
> policy to preserve only the upstream trajectory atoms that are causally
> useful for success.

Three asymmetric ideas combined into one pipeline:

1. **Outcome ablation** — strip the final outcome down to the *smallest*
   subset that the oracle still accepts. Call this the **success
   certificate**: the part of the outcome that actually mattered.
2. **Attribution** — for each atom in the certificate, trace which upstream
   trajectory atoms contributed to producing it.
3. **Policy learning** — train a model that retains only the trajectory atoms
   in the resulting **support graph**, under a token budget.

## Why this is not summarization

A summarizer asks: *what compact representation preserves the meaning of the
trajectory?* This framework asks: *what minimal subset of trajectory
information is causally sufficient for agent success?*

The targets are different. A summarizer keeps semantically central atoms; this
framework keeps **success-conditioned** atoms. The support graph is exactly
the set of trajectory atoms that, if removed, would have prevented the
outcome's certificate atoms from existing.

The thesis in one line:

> Learn a general context policy for agents by identifying the minimal
> success-critical outcome atoms, attributing them backward through the
> trajectory, and training the agent to retain only the trajectory atoms that
> causally support successful outcomes.

## The pipeline

```
Raw agent trajectory
        ↓
TrajectoryRecorder / JSONTrajectoryLoader
        ↓
GenericAtomizer  ─→  trajectory atoms + outcome atoms
        ↓
OutcomeOracle (domain-specific)
        ↓
GreedyAblator / BeamAblator / DeltaDebuggingAblator  ─→  SuccessCertificate
        ↓
HeuristicAttributor / PromptLLMAttributor  ─→  AttributionGraph
        ↓
extract_topk_support / extract_threshold_support  ─→  SupportGraph
        ↓
build_training_example  ─→  hard labels + soft labels (attribution prior)
        ↓
train_policy  ─→  LogisticContextPolicy
        ↓
compress_trajectory  ─→  retained atoms
        ↓
run_benchmark  ─→  cost-success frontier vs baselines
```

## Repository layout

```
outcome_critical_attribution/
  src/
    core/          # task, trajectory, outcome, atoms, oracle, graph
    recording/     # TrajectoryRecorder, JSON loader
    atomization/   # GenericAtomizer + text/artifact splitters
    ablation/      # greedy, beam, delta-debugging minimizers
    attribution/   # heuristic + LLM-prompt attributors, support extractors
    policy/        # dataset, model, training loop, inference
    evaluation/    # metrics, baselines, benchmark harness
    examples/      # toy research / browser / coding agents
  tests/           # unit tests for every layer
```

## Running the toy pipelines

No third-party dependencies; Python 3.10+ is enough.

```bash
cd outcome_critical_attribution
python src/examples/toy_research_agent.py
python src/examples/toy_browser_agent.py
python src/examples/toy_coding_agent.py

python -m pytest -q
```

Each example builds a tiny trajectory, runs the entire pipeline, and prints a
benchmark line comparing the learned policy against baselines (random,
recency, token-overlap, embedding similarity, BM25, summary, importance
ranking).

## Wiring in a real LLM

`PromptLLMAttributor` takes a provider-agnostic `Callable[[str], str]`:

```python
from attribution.llm_attributor import PromptLLMAttributor

def generate(prompt: str) -> str:
    # call OpenAI / Anthropic / a local model and return the reply text
    ...

attributor = PromptLLMAttributor(generate=generate)
graph = attributor.attribute(trajectory_atoms, outcome_atoms)
```

Identical interface to `HeuristicAttributor`. The framework never imports a
provider SDK.

## Plugging in a domain-specific oracle

Subclass `OutcomeOracle`. The core only ever calls `evaluate`. Examples of
what the oracle can wrap:

- **Coding** — run tests, type check, lint, apply patches, LLM judge.
- **Browser** — verify form submission, final URL, post-action DOM state.
- **Research** — fact-check answer, citation coverage, rubric judge.
- **Data analysis** — re-run a notebook, compare computed values.
- **Workflow** — check the target API/calendar/email state changed.
- **Robotics / sim** — read out simulator reward / final state.

## Metrics

Every metric in the thesis is implemented in `evaluation/metrics.py`:

- `success_retention(original, compressed)`
- `oracle_score_retention(original, compressed)`
- `compression_ratio(selected, all)`
- `token_savings(selected, all)`
- `attribution_precision / recall / f1(predicted, gold)`
- `cost_success_frontier(points)` — Pareto frontier for the headline plot.

## Status

This is a research prototype. The default attribution model is the heuristic
lexical-overlap attributor so the pipeline runs end-to-end without an LLM; the
LLM-backed attributor has full prompt construction and parsing, ready for a
generate callable. The policy is a logistic regression over hand features
trained with batch gradient descent — small enough to read, large enough to
exercise the training loss in the thesis (BCE + cost + KL-to-prior).
