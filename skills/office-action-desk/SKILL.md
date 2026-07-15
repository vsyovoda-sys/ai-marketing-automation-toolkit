---
name: office-action-desk
description: Turn explicitly scoped local exports of email, meetings, chat, calendar, tasks, and documents into a source-linked action register, decision log, risk list, drafts, and a plan-only action manifest. Use for daily/weekly work summaries, meeting follow-up, project coordination, inbox-to-actions, or cross-document office synthesis. Never guess the organization/profile, merge tenants, send messages, create events, or write back automatically.
---

# Office Action Desk

Create a read-only action desk first. Separate evidence extraction from any external mutation.

## Tenant and permission boundary

- Require the user to explicitly name the organization/profile. Never infer it from the current folder, history, or default CLI configuration.
- Keep each tenant in a separate run workspace. Cross-tenant joins are blocked by default.
- Require a local export or read-only source manifest with purpose, time range, rights, and allowed actions.
- Preserve source ID and timestamp for every action, decision, and risk.
- Unknown owner or due date stays `待确认`; AI does not assign responsibility from tone.
- Drafts remain drafts. External operations become a `plan_only` manifest and are never committed by this toolkit.

## Start the Loop

```bash
python3 scripts/loopctl.py init workflows/office-action-desk.json \
  --workspace ./runs/office-001 \
  --input source_manifest=./inputs/source-manifest.json \
  --input office_exports=./inputs/office-export.json
```

## Execute phases

1. `preflight`: verify tenant/profile, source scope, time zone, purpose, rights, and cross-tenant isolation.
2. `normalize`: retain source IDs, normalize time, and mark duplicate candidates without deleting them.
3. `extract`: produce action, decision, and risk records with source links and uncertainty.
4. `owner_review`: obtain human confirmation of owners, dates, priorities, and unresolved items.
5. `drafts`: prepare local summaries and communication drafts; do not assume recipients.
6. `action_preview`: create a plan-only manifest bound to tenant, profile, actor, target, exact diff, quantity, input fingerprint, cost cap, and TTL.
7. `delivery`: scan and deliver locally. Confirm no external commit occurred.

Use `scripts/action_manifest.py` to create the preview. It intentionally has no send/commit command.

## Recovery rules

- Mixed tenants: stop, split sources, and initialize separate runs.
- Time-zone ambiguity: retain original time plus normalized time and request confirmation.
- Conflicting owner/date: preserve both sources and mark unresolved.
- Connector or authentication problem: do not bypass scope or switch to an unauthorized scraper; use a user export.
- Input change after approval: invalidate downstream approval through `change-input`.

## Required deliverables

`normalized-index.json`, `action-register.csv`, `decision-log.md`, `risk-list.md`, `office-pack.md`, `action-manifest.json`, and `delivery-manifest.json`.
