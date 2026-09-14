# Bude Helpdesk market roadmap

Research date: 5 August 2026
Product baseline: Bude Helpdesk Flutter `0.1.0` plus `bude_api` over standard
Frappe Helpdesk DocTypes.

## Product position

Bude should not sell another ticket database. Frappe Helpdesk is open source,
supports unlimited agents and tickets, and can be self-hosted. Bude should sell
the operational layer around it: guided rollout, a production-grade mobile
workspace, measurable SLA improvement, ERPNext context, managed integrations,
and ongoing service optimization.

The initial ideal customer is an ERPNext/Frappe organization with 3-50 support
or field-service agents, especially distributors, equipment/service companies,
internal IT teams, and multi-site operators. They value data ownership but lack
the time or specialist skills to turn upstream Helpdesk into a reliable support
operation.

## Existing product audit

The current Flutter app and backend already cover:

- requester and agent queues with filters and local saved views;
- ticket creation, replies, internal notes, attachments, assignment, status
  transitions, SLA context, templates, saved replies, and article suggestions;
- related tickets, activity, team availability, customer organization/contact
  context, and field-service check-in, check-out, and visit completion;
- offline ticket/reply drafts, retry queue, secure token storage, Google login,
  push registration, English/Arabic UI, and light/dark themes.

The backend keeps Frappe Helpdesk as the system of record and adds no custom
ticket DocTypes. Agent-only endpoints are role gated; requester reads are scoped
to the session identity. The commercial gap is less about ticket CRUD and more
about onboarding, prioritization, automation, channel reliability, reporting,
and proving support outcomes.

## Current pain-point evidence

The evidence is directional, not a statistically representative survey. It
combines current upstream user reports with official product and pricing
material and must be validated in paid pilots.

| Pain | Evidence | Product implication |
|---|---|---|
| Agents waste time choosing the next ticket | Upstream issue [#3183](https://github.com/frappe/helpdesk/issues/3183) asks for an SLA-, priority-, and age-sorted queue with one-click pull | Make guided next work and SLA risk the mobile agent home |
| Managers lack useful KPI views | Issues [#3619](https://github.com/frappe/helpdesk/issues/3619) and [#3234](https://github.com/frappe/helpdesk/issues/3234) request editable dashboards and response/resolution/feedback summaries | Sell operational dashboards and scheduled service reviews |
| Notifications and email workflows are fragile | Reports include portal notifications [#1961](https://github.com/frappe/helpdesk/issues/1961), reply delivery [#3092](https://github.com/frappe/helpdesk/issues/3092), and forwarding with attachments [#2141](https://github.com/frappe/helpdesk/issues/2141) | Add delivery health, retries, auditability, and managed channel setup |
| Customer activation is too technical | A [portal access report](https://discuss.frappe.io/t/helpdesk-customer-portal-access-for-customers/147430) describes manual invitation and confusing portal routing; a small G2 sample flags advanced configuration complexity | Provide setup health, guided invites, and activation measurement |
| Teams need deeper ERPNext context | Issue [#3564](https://github.com/frappe/helpdesk/issues/3564) requests Contact/Customer membership synchronization | Differentiate through safe ERPNext customer, asset, warranty, and service context |
| Escalation policies are incomplete | Issue [#2050](https://github.com/frappe/helpdesk/issues/2050) requests second-level escalation after repeated reopenings | Offer configurable escalation with an audit trail |
| Customers expect more channels | WhatsApp request [#1622](https://github.com/frappe/helpdesk/issues/1622) remains open | Add channels as managed, usage-priced connectors after the core queue is reliable |
| Installation/upgrades consume expert time | Reports include v15 install failure [#3527](https://github.com/frappe/helpdesk/issues/3527) and missing Docker app images [#3227](https://github.com/frappe/helpdesk/issues/3227) | Monetize managed deployment, compatibility checks, backups, and upgrades |

Official Helpdesk documentation confirms that SLA, assignment rules, portal,
knowledge base, saved replies, and custom views are already upstream features.
The roadmap operationalizes them rather than rebuilding them. Frappe's
[pricing](https://frappe.io/helpdesk/pricing) starts with low-cost hosting,
permits free self-hosting, and does not charge per agent. Published annual
pricing is currently $19/$55/$89 per agent per month for
[Freshdesk](https://www.freshworks.com/freshdesk/pricing/) and $55-$169 for
[Zendesk Suite](https://support.zendesk.com/hc/en-us/articles/5555300573850-Zendesk-s-2023-Pricing-Update-What-You-Need-To-Know).
That leaves room to price managed outcomes below incumbent seat-based cost at
team scale without pretending the open-source core is proprietary.

## Packaging hypothesis

Pricing is a pilot hypothesis, excluding hosting, taxes, provider usage, and
exceptional custom development.

| Package | Buyer and outcome | Included | Commercial hypothesis |
|---|---|---|---|
| Launch | 3-10 agents leaving shared email | Managed deployment, branded apps, email intake, portal, base SLA, training, backup/upgrade runbook | ₹35,000 / US$399 setup + ₹8,000 / US$99 monthly |
| Operations | 5-30 agent or field-service team | Launch plus Support Pulse, automation, service review, notification health, ERPNext context, standard integrations | ₹1,25,000 / US$1,499 setup + ₹25,000 / US$299 monthly |
| Enterprise | Multi-team, multi-site, regulated, or integration-heavy operation | Operations plus SSO/security review, custom dashboards, channels, sandbox/release management, priority support | from ₹4,50,000 / US$5,000 setup + ₹85,000 / US$999 monthly |

WhatsApp/telephony, field service, migration, bespoke ERPNext integration, and
AI are add-ons. Provider usage should be passed through transparently.

## Release roadmap

Every release is additive, uses capability checks for version-dependent fields,
preserves the API envelope, and must pass backend tests, Flutter analysis/tests,
and Android/Web release builds before promotion.

### 0.2 — Support Pulse and guided next work (implemented)

- Agent-only dashboard with open, unassigned, urgent, overdue, and due-soon
  counts, plus team/priority workload breakdowns.
- SLA-first next-work queue, then priority and age; unassigned work is preferred.
- One-tap self-assignment, direct handoff, and a bounded-scan warning.
- No new DocTypes and no permission bypass.

Pilot success: 90% of eligible tickets picked from Next Up, 20% lower median
assignment latency, and fewer preventable SLA breaches over four weeks.

### 0.3 — Setup Health and customer activation (implemented)

- Manager-only, read-only preflight for Helpdesk/Frappe compatibility, upstream
  setup completion, incoming/outgoing email, scheduler, agents, teams, SLA,
  portal roles/default role, public URL, backup review, and FCM credentials.
- Customer activation funnel based on standard `HD Customer Member`, `Contact`,
  `User`, and `Has Role` records. Activation is the first observed login after
  an enabled portal account receives `HD Customer` or `HD Customer Manager`.
- Guided handoff to the upstream Customers invitation flow, which continues to
  own invitations, role changes, expiry, and email delivery.
- Evidence-based launch test for portal access, customer intake, ticket
  assignment, and an outbound reply. No synthetic production tickets are
  created by the diagnostic.
- English/Arabic manager UI, bounded 500-membership scan, no returned customer
  identities or configuration secrets, and additive API compatibility.

Paid gate: Launch onboarding; continuous health in Operations. Target: first
real ticket within one business day and >70% invited-customer activation.

Certification target: Frappe majors 15 and 16 with a migrated Helpdesk site.
The customer-role check reflects Helpdesk 1.28's explicit `HD Customer` and
`HD Customer Manager` portal permission model. See the
[0.3 release runbook](release-0.3.md) for rollout and rollback.

### 0.4 — Automation and escalation pack (implemented)

- Policies for inactivity, due-soon, breach, unassigned, VIP, and repeated
  reopenings; idempotent evaluation, delivery log/retry, and audit trail.
- Manager digest and agent activity notifications.
- Manager-only mobile workspace for dry-run previews, delivery health, recent
  audit events, manual evaluation, and bounded failed-delivery retries.
- Explicit site-level opt-in, 500-ticket scan cap, three-attempt retry cap, and
  no custom DocTypes: standard `Notification Log` and `Integration Request`
  records provide delivery and audit durability.

Paid gate: Operations. Target: >95% escalation delivery and 30% fewer manually
chased tickets.

Release target: `0.4.0+202608052`. See the
[0.4 release runbook](release-0.4.md) for configuration, rollout, metric
definitions, and rollback.

### 0.5 — Reliable omnichannel (implemented)

- Agent forwarding through Frappe's standard email queue, with strict recipient
  validation and attachments limited to the selected ticket conversation.
- Per-ticket email/WhatsApp/phone activity plus manager email acceptance,
  provider readiness, and masked audit health; raw queue errors and credentials
  never reach the app.
- Provider-neutral WhatsApp connector with HTTPS-only server configuration,
  approved templates, explicit consent evidence, ticket-contact-only E.164
  identity matching, deterministic idempotency, and three-attempt limits.
- Telephony activity bridge using standard `Communication` and
  `Integration Request` records, compatible with native Telephony when present.
- English/Arabic agent workspace and manager-only channel health screen. No
  custom DocTypes or upstream Helpdesk fork.

Paid gate: per-channel add-on plus usage. Target: >99% accepted delivery and no
cross-customer conversation leakage.

Release target: `0.5.0+202608053`. See the
[0.5 release runbook](release-0.5.md) for provider contract, configuration,
rollout, metric definitions, and rollback.

### 0.6 — Knowledge deflection and agent acceleration

- Search analytics, zero-result topics, ticket-to-article review, freshness
  ownership, and verified deflection measurement.
- Optional cited retrieval-based drafts with approval, tenant isolation, and
  cost caps; no silent autonomous sending.

Paid gate: Operations analytics; AI by included usage/outcome. Target: 15%
verified deflection without lowering CSAT.

### 0.7 — ERPNext Customer 360 and Service Cloud bridge

- Contact/HD Customer membership diagnostics, orders, invoices, installed
  equipment, warranty/AMC, maintenance, and service-work-order handoff under
  existing permissions.
- Customer health and renewal/service revenue signals.

Paid gate: Enterprise/industry pack. Target: 25% less context switching and a
measurable service-to-renewal pipeline.

### 1.0 — Enterprise insight and governance

- Role-safe custom dashboards, trends, response/resolution/CSAT review, exports,
  scheduled reports, and documented metric definitions.
- SSO, audit/export controls, retention, recovery exercise, performance budgets,
  accessibility audit, upgrade matrix, and optional sampled conversation QA.

Paid gate: Enterprise. Target: signed operational review, successful recovery
exercise, zero critical permission leaks, and agreed performance objectives.

## Delivery controls

For every release:

1. Record assumptions and target upstream versions.
2. Add backend authorization, validation, happy-path, and fallback tests.
3. Add repository mapping and non-trivial widget tests.
4. Run the complete backend suite, Flutter analysis/tests, and release APK/Web
   builds; retain artifact hashes.
5. Pilot additively, measure the stated outcome, and document rollback.
6. Promote only after permission checks and a real-bench smoke test.

Do not fork Frappe Helpdesk core. Keep integrations in `bude_api`, prefer
standard DocTypes, and review any new Service Cloud schema separately.
