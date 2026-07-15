---
name: campaign-ops
description: "Orchestrate an end-to-end marketing campaign from brief diagnosis through KPI contract, strategy, work packages, asset readiness, independent launch review, and a plan-only launch pack. Use for campaigns, launches, UGC programs, PR activations, content operations, or cross-team marketing delivery. This is an orchestrator: it must reference verified research, content, media, office, and KPI artifacts rather than claiming those subtasks are complete."
---

# Campaign Ops

Coordinate a campaign as a graph of evidence-backed work packages. A strategy deck is not proof that research, assets, owners, budgets, or monitoring are ready.

## Boundaries

- Require an explicit decision owner, budget, timeline, KPI formula, pause threshold, and kill threshold.
- Reference child Loop artifacts and their verification evidence. Do not regenerate a shallow substitute inside this skill.
- Never silently relax budget, platform, rights, or resource constraints.
- Launch approval only approves a local pack. This skill never publishes, spends, messages, or writes remotely.
- When evidence or rights fail, return to the appropriate child Loop.

## Start the Loop

```bash
python3 scripts/loopctl.py init workflows/campaign-ops.json \
  --workspace ./runs/campaign-001 \
  --input campaign_brief=./inputs/campaign-brief.md \
  --input resource_contract=./inputs/resources.json \
  --input evidence_pack=./inputs/evidence-pack.json
```

## Execute phases

1. `brief_diagnosis`: find contradictions and missing goal, audience, owner, time, budget, channel, evidence, and rights.
2. `success_contract`: a human approves metric definitions, data delay, decision owner, pause, and termination rules.
3. `strategy`: connect insight to mechanism, content architecture, and KPI. Facts come from the evidence pack.
4. `work_packages`: give every task an input, output, owner, date, budget, dependency, and acceptance test.
5. `asset_readiness`: verify child Loop evidence for research, content, media, coordination, and monitoring.
6. `launch_review`: an independent owner approves, revises, or rejects; confirm fallback and rollback readiness.
7. `launch_pack`: create a redacted local pack and `plan_only` action manifest. Do not execute it.

Drive each phase with `loopctl.py`. A file's existence is not a readiness check.

## Recovery routing

- Unsupported claim → `research-to-brief`.
- Missing or unverified copy → `content-repurpose`.
- Missing media rights/render QA → `media-production`.
- Unclear owners or cross-tenant data → `office-action-desk`.
- Undefined or unreliable KPI → `kpi-monitor-diagnose`.
- Resource or budget infeasibility → return violated constraints; do not fake a balanced plan.

## Required deliverables

`gap-list.md`, `kpi-contract.json`, `strategy.md`, `work-packages.csv`, `readiness.md`, `launch-decision.md`, `launch-pack.md`, and `action-manifest.json`.
