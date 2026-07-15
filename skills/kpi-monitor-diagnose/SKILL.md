---
name: kpi-monitor-diagnose
description: Define a versioned KPI contract, validate metric data, detect pre-specified anomalies, separate data issues from natural variation and business change, build a multi-hypothesis diagnosis, and produce a human-reviewed readout. Use for campaign, creator, product, content, or office KPI monitoring and postmortems. Do not use to auto-change budgets, stop campaigns, or claim causality from a single correlation.
---

# KPI Monitor and Diagnose

Diagnose only after metric definition and data quality pass. “The metric moved” is not yet a business explanation.

## Boundaries

- Require formula, numerator/denominator, unit, time zone, baseline, target, freshness, allowed delay, threshold, and owner.
- Version metric definitions. Never compare two periods with silently changed logic.
- Detect anomalies using pre-specified rules; do not move thresholds after seeing the result.
- Check data problems and expected variation before generating business stories.
- Provide competing explanations, disconfirming evidence, and a smallest next check.
- A responsible human decides actions. The toolkit never reallocates spend or changes external state.

## Start the Loop

```bash
python3 scripts/loopctl.py init workflows/kpi-monitor-diagnose.json \
  --workspace ./runs/kpi-001 \
  --input metric_contract=./inputs/metric-contract.json \
  --input metric_data=./inputs/metrics.csv
```

## Execute phases

1. `contract_review`: a human approves formula, denominator, time zone, delay, threshold, and decision owner.
2. `data_quality`: validate schema, types, denominator, missingness, duplicates, version, and freshness.
3. `detect`: apply the pre-registered threshold to a comparable baseline.
4. `classify`: distinguish data issue, expected variation, or possible business change; preserve uncertainty.
5. `diagnose`: build a hypothesis tree with evidence, alternatives, counterevidence, and next checks.
6. `decision_review`: a human chooses investigate/hold/pause/propose action; bound cost and impact.
7. `readout`: include definitions, data status, limitations, diagnosis, decision, and next measurement. Any action remains plan-only.

Use `loopctl.py` throughout. Run `data_quality.py` for the raw CSV when applicable.

## Recovery rules

- Missing denominator or stale data: stop business diagnosis and report a data incident.
- Definition changed: split the series or recompute comparable history; do not join incompatible periods.
- One attractive explanation dominates: force at least one plausible alternative and a disconfirming test.
- Small sample: report uncertainty and observation; avoid universal or causal language.
- Repeated failure: enter `99_exception_queue`; do not reword the same request indefinitely.

## Required deliverables

`approved-contract.json`, `quality-report.json`, `anomaly-list.csv`, `diagnosis.md`, `next-checks.csv`, `decision.md`, and `kpi-readout.md`.
