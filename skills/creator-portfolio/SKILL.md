---
name: creator-portfolio
description: Build an explainable creator shortlist and budget portfolio from an authorized local export, including data profiling, stable-key duplicate candidates, evidence-backed matching, human calibration, constraint solving, and a plan-only delivery manifest. Use for creator buying, KOL/KOC selection, PR seeding, ambassador shortlists, or partnership portfolios. Do not use to bypass platform access controls, infer sensitive traits, or auto-contact creators.
---

# Creator Portfolio

Create a decision system that explains who was included, excluded, or escalated. Do not disguise scraping or demographic inference as “AI matching.”

## Hard gates

- Accept only an authorized export or user-provided dataset. Never bypass login, CAPTCHA, API scope, robots rules, or rate limits.
- Keep raw value, normalized value, match evidence, confidence, and review status together.
- Treat duplicates as candidates; never delete or merge originals automatically.
- Do not infer gender, ethnicity, health, age, income, or other sensitive traits from names, images, language, or proxies.
- A business owner, not the scoring agent, approves weights and thresholds.
- Do not write to a CRM, spreadsheet, platform, or email tool. Generate a `plan_only` action manifest.

## Start the Loop

```bash
python3 scripts/loopctl.py init workflows/creator-portfolio.json \
  --workspace ./runs/creator-001 \
  --input portfolio_brief=./inputs/portfolio-brief.md \
  --input creator_data=./inputs/creators.csv \
  --input data_rights=./inputs/data-rights.json
```

Profile the CSV before asking a model to reason about it:

```bash
python3 scripts/data_quality.py ./inputs/creators.csv \
  --key platform --key creator_id \
  --output ./runs/creator-001/10_work/quality-report.json
```

## Execute phases

1. `preflight`: lock goal, currency, tax, budget bounds, allowed fields, and data rights.
2. `quality_profile`: freeze the input fingerprint; report schema, rows, nulls, stable keys, and duplicate candidates.
3. `match_and_features`: normalize and match with boundary-aware rules. Route ambiguity to an exception queue.
4. `calibration`: review boundary, stratified, and low-confidence samples. Approve scoring only with human evidence.
5. `portfolio`: calculate feasible combinations. Prove budget conservation including tax and fees.
6. `decision_review`: let the responsible person choose, revise, or reject; record the rationale.
7. `delivery`: rebuild from allowed fields and create a plan-only action manifest.

Use `loopctl.py start/record/verify/complete` for every phase. Only deterministic checks or explicit human records can release a phase.

## Recovery rules

- Empty values, short substrings, or fuzzy names can never create a high-confidence match.
- If field mapping fails, stop before scoring and produce a mapping exception report.
- If no feasible portfolio exists, return violated constraints. Never silently loosen budget or bans.
- A second attempt must change mapping, evidence, or explicit constraints; cosmetic re-prompting is not recovery.
- After the retry budget, preserve the snapshot and move unresolved items to `99_exception_queue`.

## Required deliverables

`quality-report.json`, `feature-table.csv`, `scoring-contract.json`, `portfolio-options.csv`, `decision.md`, `portfolio-delivery.csv`, and `action-manifest.json`.
