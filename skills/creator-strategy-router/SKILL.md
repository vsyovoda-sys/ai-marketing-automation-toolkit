---
name: creator-strategy-router
description: Route a brand buyer, agency, creator, AI IP, artist team, or product GTM user to the correct creator strategy workflow based on their goal, authorized platform access, and data rights. Use before creator procurement, influencer buying, social positioning, creator benchmarking, or platform content strategy. Do not use to bypass platform access controls, bulk-harvest restricted creator data, or redistribute account databases.
---

# Platform Creator Strategy Router

## Make the entry decision first

Ask only for:

1. The subject: brand, agency, creator, AI IP, artist team, or product.
2. The decision: buy creator collaborations, find a content position, or both.
3. The platform and account capability: account role, already logged-in surfaces, export/API permission, and allowed use.
4. Existing materials: creator export, owned account analytics, content samples, product evidence, or none.

Store this in `strategy_request` and `access_profile`. Treat a claimed login as unverified until a human confirms the visible account role and permitted data surface. Start from `templates/access-profile.example.json`; a missing platform, visible role, permitted page, export/API scope, allowed fields, purpose, retention period, private destination, authorizer, or date means the router may only deliver an access report.

## Route deterministically

| Condition | Route | Do not do |
|---|---|---|
| The decision is creator procurement and the user has verified official procurement access, an authorized export/API, or documented delegated authority | `creator-portfolio` | Do not use creator search to infer private traits or start outreach automatically. |
| The account is creator-side/inspiration-only, or the user lacks verified procurement authority | `platform-positioning-benchmark` | Do not fabricate a creator purchase list. |
| The goal contains both | Default to positioning first; if procurement authority is already verified, the two research paths may run in parallel with strictly separated data. | Do not treat reference accounts as purchasable creators. |
| Access or rights are unclear | Stop at an access report. | Do not scrape, paginate, reuse a login, or silently switch to another data source. |

## Collection boundary

- This v1.1 toolkit does not connect to, click through, or extract from a live platform. It creates an access contract and an export/collection specification; the user completes any official export in their authorized system, then imports the permitted local result.
- Prefer official export or documented API. A future live connector would need separate platform-terms, tenant, credential, and rate-limit review.
- A visible page is not permission to build or publicly distribute a full creator database. Before any bulk capture, require explicit authorization, a terms-compatible method, an allowed field list, retention period, and a private destination.
- Course reference material must be derived, time-stamped, source-linked, field-minimized, and refreshable. Keep personal data, login artifacts, raw restricted exports, and creator contact details out of the public repository.
- If a platform does not expose a buyer-facing creator pool to this user, use owned analytics, platform-native inspiration/trend surfaces, allowed public references, and manual examples for positioning research.

## Deliver a handoff, not a vague recommendation

Output:

- route decision and reasons;
- verified access boundary and prohibited actions;
- minimal input list for the child Loop;
- missing capability/data list;
- a copyable next-Loop prompt.

Use `workflows/creator-strategy-router.json` with `loopctl.py`. Do not let the model self-approve the user role, rights, or route.
