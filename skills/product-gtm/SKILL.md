---
name: product-gtm
description: Convert product evidence into scoped ICP/JTBD hypotheses, an evidence-backed claim matrix, message architecture, and a pre-registered small channel experiment with budget and stopping rules. Use for software or hardware GTM, product launches, positioning, messaging, channel selection, or early market tests. Do not use to invent product capabilities, target sensitive groups, or auto-launch paid experiments.
---

# Product GTM

Run two connected but independently stoppable subgraphs: a positioning evidence pack, then a bounded channel experiment. Do not jump from feature notes to campaign copy.

## Safety and evidence rules

- Record product version, test date, evidence type, known limitation, market, and jurisdiction.
- Separate verified function, expected value, and unverified promise.
- Each claim points to evidence and states scope. Remove unsupported superlatives and causal claims.
- Define ICP by observable job and context, not inferred sensitive traits.
- Pre-register primary metric, budget/sample cap, stop rule, and decision rule.
- Generate a local experiment pack only. Never publish, spend, or create accounts.

## Start the Loop

```bash
python3 scripts/loopctl.py init workflows/product-gtm.json \
  --workspace ./runs/gtm-001 \
  --input product_evidence=./inputs/product-evidence.json \
  --input market_request=./inputs/market-request.md
```

若只需要定位证据包，在 `init` 增加 `--target positioning-only`；runner 会在 `message_pack` 完成后把本次运行标为 completed。默认目标是 `full-experiment`。

## Subgraph A: positioning evidence

1. `evidence_preflight`: inventory functions, limitations, versions, rights, market, and missing proof.
2. `positioning`: write scenario/JTBD/ICP hypotheses with evidence, counterexamples, and alternatives.
3. `claim_matrix`: connect function → value → claim → evidence → limit → banned wording.
4. `message_pack`: develop message hierarchy and channel hypotheses without adding new claims.

`positioning-only` 目标在这里正式完成；后续实验阶段不会进入 ready 列表。

## Subgraph B: channel experiment

5. `experiment_contract`: a human approves a falsifiable hypothesis, metric, cap, stop condition, and decision rule.
6. `experiment_pack`: create controlled variants and a `plan_only` action manifest. Change only the declared factor.
7. `learning_template`: define quality checks, alternative explanations, result boundaries, and next decision before results arrive.

Use `loopctl.py start/record/verify/complete`. Keep model judgment in assistive phases; evidence checks and budget equations must be deterministic or human-approved.

## Recovery rules

- Weak evidence: return a gap; do not compensate with market language.
- Broad ICP: rewrite around a concrete job, trigger, barrier, and alternative.
- No differentiator: describe trade-offs rather than invent uniqueness.
- Mixed experiment variables: simplify until the primary factor is interpretable.
- Small/noisy result: record an observation, not a universal causal conclusion.
- Any input change invalidates downstream claims and approval through `change-input`.

## Required deliverables

`evidence-inventory.csv`, `positioning-hypotheses.md`, `claim-matrix.csv`, `message-architecture.md`, `experiment-contract.json`, `experiment-pack.md`, `action-manifest.json`, and `learning-template.md`.
