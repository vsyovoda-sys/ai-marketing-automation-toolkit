---
name: platform-positioning-benchmark
description: Build an evidence-backed social-platform positioning and content experiment plan for a creator, AI IP, artist team, or product GTM user using authorized account data, platform-native insight surfaces, and cited public references. Use when the user needs to find their place on Xiaohongshu, Douyin, Bilibili, Weibo, WeChat Channels, Official Accounts, or another platform but does not need to buy creators. Do not claim unknown recommendation weights, bulk-scrape restricted account data, or guarantee distribution outcomes.
---

# Platform Positioning Benchmark

## Read the right reference first

Read `references/platform-mechanism-evidence.zh-CN.md` before making platform-mechanism claims. It separates:

- official/publicly disclosed mechanism evidence;
- observable account and content signals;
- unverified hypotheses to test;
- prohibited claims, especially invented fixed algorithm weights.

## Input contract

Require:

1. `positioning_request`: who or what is being positioned, target audience, platform, market, commercial goal, and time window.
2. `access_profile`: owned accounts, already logged-in creator/inspiration/data surfaces, export rights, and prohibited actions.

Optionally accept `owned_evidence`: historical account metrics, content samples, product proof, customer feedback, or source-linked public references.

If data is missing, produce an evidence-gap list. Do not replace it with a scraped full-platform account list.

## Build the positioning in this order

1. Confirm the subject, target decision, platform role, and allowed data sources.
2. Create a mechanism evidence ledger. Mark every statement `official`, `observed`, `hypothesis`, or `unknown`.
3. Build a field-minimized reference cohort from cited examples. Each row records source URL, discovery date, evidence level, public/authorized status, redistribution restriction, content role, topic, format, user problem, interaction signal, and evidence quality; never add contact details or imply the cohort is a purchasable creator list.
4. Generate two or more falsifiable positioning options and content pillars.
5. Design small experiments with one main variable at a time, a measurement window, leading and lagging signals, stop conditions, and a next-learning decision.
6. Require a business owner to approve assumptions before the final positioning pack.

## Measurement rules

- Do not equate likes, CPE, or follower count with a platform recommendation weight.
- Measure content response using the metrics that the user is authorized to see; keep reach, consumption, interaction, search/follow/conversion, and negative feedback separate.
- Platform recommendation systems personalize, filter, diversify, and change. Every mechanism-ledger statement records its source URL, publisher, publication/access date, scope, and evidence level; unsourced or stale claims are downgraded to `hypothesis` or `unknown`. Use short experiments to learn for this account and audience; do not promise traffic.
- Do not infer sensitive traits about viewers or creators from names, images, language, or proxies.

## Deliverables

Deliver a source-linked mechanism evidence ledger, content taxonomy, reference cohort, evidence gaps, positioning options, content pillars, experiment plan, measurement contract, and a reviewed positioning pack.

Use `workflows/platform-positioning-benchmark.json` with `loopctl.py`. It is a positioning Loop, not a publishing, paid-media, or creator-outreach executor.
