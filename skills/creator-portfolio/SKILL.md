---
name: creator-portfolio
description: Build an explainable creator shortlist and budget portfolio for a brand or agency buyer after creator-strategy-router confirms authorized procurement access. Use official authorized exports, APIs, or an already-permitted procurement surface to create a private candidate snapshot, then profile data, preserve duplicate candidates, calibrate human-approved scoring, solve budget constraints, and generate a plan-only delivery manifest. Use for creator buying, KOL/KOC selection, PR seeding, ambassador shortlists, or partnership portfolios. Do not use for personal creator positioning, to bypass platform access controls, bulk-redistribute creator databases, infer sensitive traits, or auto-contact creators.
---

# Creator Portfolio

Create a procurement decision system that explains who was included, excluded, or escalated. Do not disguise scraping or demographic inference as “AI matching.”

## Hard gates

- Run `$creator-strategy-router` first unless the user has supplied a signed-off `entry_assessment` confirming brand/agency procurement access. A creator, AI IP, product team, or user without procurement access belongs in `$platform-positioning-benchmark`.
- This v1.1 toolkit never logs into, clicks through, or extracts from a live procurement platform. It accepts an authorized export/API result that the user has obtained, or produces an export specification for the user to run in their authorized system. Never bypass login, CAPTCHA, API scope, robots rules, rate limits, or platform terms.
- Do not make a course-wide creator database from paginated account pages. Bulk capture needs explicit authorization, a terms-compatible method, minimum fields, a retention period, and a private destination.
- Keep raw value, normalized value, match evidence, confidence, and review status together.
- Treat duplicates as candidates; never delete or merge originals automatically.
- Do not infer gender, ethnicity, health, age, income, or other sensitive traits from names, images, language, or proxies.
- A business owner, not the scoring agent, approves weights and thresholds.
- Do not write to a CRM, spreadsheet, platform, or email tool. Generate a `plan_only` action manifest.

## Start the Loop

```bash
python3 scripts/loopctl.py init workflows/creator-portfolio.json \
  --workspace ./runs/creator-001 \
  --input entry_assessment=./inputs/entry-assessment.md \
  --input access_profile=./inputs/access-profile.json \
  --input portfolio_brief=./inputs/portfolio-brief.md \
  --input data_rights=./inputs/data-rights.json
```

If an approved `creators.csv` already exists, include `--input creator_data=./inputs/creators.csv`. Otherwise complete `candidate_snapshot` first: let the agent produce an export specification; the user performs the export through the confirmed authorized route and imports the resulting permitted local CSV as the candidate snapshot.

Profile the final snapshot before asking a model to reason about it:

```bash
python3 scripts/data_quality.py ./inputs/creators.csv \
  --key platform --key creator_id \
  --output ./runs/creator-001/10_work/quality-report.json
```

## Execute phases

1. `entry_route`: confirm buyer route and access boundary; otherwise stop and hand off to positioning.
2. `preflight`: lock goal, currency, tax, budget bounds, allowed fields, and data rights.
3. `candidate_snapshot`: reuse an approved export or create a private, source/time-stamped export specification for the user to execute through the authorized route.
4. `quality_profile`: freeze the snapshot fingerprint; report schema, rows, nulls, stable keys, and duplicate candidates.
5. `match_and_features`: normalize and match with boundary-aware rules. Route ambiguity to an exception queue.
6. `candidate_evidence`: for every proposed final candidate, record permitted account-content or recent-work evidence, its timestamp, field permission, fit rationale, and review state; output an `eligible_creator_pool` keyed by stable ID. An account with only aggregate metrics remains pending—not recommended.
7. `calibration`: review boundary, stratified, and low-confidence samples. Approve scoring only with human evidence.
8. `portfolio`: calculate feasible combinations. Prove budget conservation including tax and fees.
9. `decision_review`: let the responsible person choose, revise, or reject; record the rationale.
10. `delivery`: rebuild from allowed fields and create a plan-only action manifest.

Use `loopctl.py start/record/verify/complete` for every phase. Only deterministic checks or explicit human records can release a phase.

## Recovery rules

- Empty values, short substrings, or fuzzy names can never create a high-confidence match.
- If field mapping fails, stop before scoring and produce a mapping exception report.
- Final recommendations may draw only from `eligible_creator_pool`: each candidate needs permitted account-content or recent-work evidence. Aggregate performance fields alone can form a candidate pool, never a final recommendation.
- Candidate-pool metrics, CPE, commercial indices, and rankings are procurement signals. They are not a platform's natural-recommendation formula.
- If no feasible portfolio exists, return violated constraints. Never silently loosen budget or bans.
- A second attempt must change mapping, evidence, or explicit constraints; cosmetic re-prompting is not recovery.
- After the retry budget, preserve the snapshot and move unresolved items to `99_exception_queue`.

## Required deliverables

`collection-audit.md`, `quality-report.json`, `feature-table.csv`, `creator-evidence-ledger.csv`, `scoring-contract.json`, `portfolio-options.csv`, `decision.md`, `portfolio-delivery.csv`, and `action-manifest.json`.
