# Bude Helpdesk 0.5 release runbook

Release: `0.5.0+202608053`

Scope: Reliable omnichannel

Target: migrated Helpdesk on Frappe 15 or 16

## What ships

- ticket email forwarding through Frappe's standard Communication and Email
  Queue path, including up to 10 files already attached to that ticket or one
  of its linked communications;
- per-ticket delivery/activity history using standard Communication delivery
  state, the latest related Email Queue state, and attachment counts;
- manager channel health for outgoing email accounts, the latest 500 queue
  rows, WhatsApp readiness, Telephony availability, and provider audit results;
- an opt-in, provider-neutral WhatsApp template webhook and standard Chat
  Communication audit after provider acceptance;
- an idempotent phone activity bridge using standard Phone Communications;
- an English/Arabic agent channel workspace and manager-only `/admin/channels`.

No custom DocType or schema migration is added. WhatsApp is disabled by default.
Email forwarding uses the site's existing outgoing email account. Neither
provider tokens nor raw email queue error text is returned to the mobile app.

## WhatsApp provider contract

Configure the connector only after the provider adapter is deployed behind
HTTPS. The app sends `POST` with `Content-Type: application/json` and
`Authorization: Bearer <server-side token>`:

```json
{
  "event": "helpdesk.message.send",
  "channel": "whatsapp",
  "ticket": "HD-0001",
  "to": "+15551234567",
  "template": "ticket_update",
  "variables": {},
  "consent_reference": "CRM consent #12, 2026-08-05",
  "idempotency_key": "<sha256>"
}
```

Any HTTP 2xx response with an optional JSON object is acceptance. All other
responses are failures. The adapter must treat `idempotency_key` as unique and
return the original result for a repeat. This is essential because a provider
may accept a message immediately before the site transaction fails. The token
and full destination number are not written to the audit row; the phone is
masked and the agent-provided consent reference is retained as audit evidence.

## Configuration

Store secrets in site configuration, not in the Flutter bundle or a DocType:

```shell
bench --site <site> set-config bude_helpdesk_whatsapp_endpoint "https://adapter.example.com/v1/messages"
bench --site <site> set-config bude_helpdesk_whatsapp_token "<secret>"
bench --site <site> set-config bude_helpdesk_whatsapp_templates '["ticket_update","resolved"]' --parse
bench --site <site> set-config bude_helpdesk_whatsapp_enabled 1
```

The endpoint must be HTTPS and cannot contain embedded credentials. Template
names are an allowlist. Each WhatsApp action requires a 3-200 character consent
reference and an 8-100 character request key. Delivery stops after three failed
attempts for the same ticket/request key.

The ticket must link one exact Contact with one unambiguous E.164 number. If its
phone and mobile fields contain different valid numbers, the action is blocked
for human correction. Agents cannot type or override the provider destination.
The same identity rule applies to phone activity.

## Deploy and activate

1. Back up the site and retain an off-site copy.
2. Deploy `bude_api`, install normal bench dependencies, and run
   `bench --site <site> migrate`.
3. Restart web, scheduler, and worker processes.
4. Publish the Android APK/Web bundle and install version `0.5.0`.
5. Sign in as an Agent Manager and open Channel health. Confirm the intended
   outgoing account and inspect the recent email acceptance baseline.
6. As an Agent, open a pilot ticket, then Channels & delivery. Forward one
   ticket-owned attachment to a controlled external mailbox.
7. Leave WhatsApp disabled until the adapter passes its authentication,
   idempotency, approved-template, consent, and destination tests.
8. Enable WhatsApp for a consented pilot contact, send one approved template,
   repeat the same request key at the API, and confirm only one provider action.
9. Log one inbound and outbound call and verify both appear on the ticket.

## Smoke test

1. Confirm customers cannot access agent channel actions and plain Agents cannot
   access manager channel health.
2. Try a mixed valid/invalid recipient list and confirm the entire forward is
   rejected. Try a File from another ticket and confirm it is rejected.
3. Confirm a successful forward creates a linked Communication/Email Queue row
   with only the selected attachments.
4. Confirm raw Email Queue error content is absent from API and app responses.
5. With WhatsApp disabled or incomplete, confirm no provider request is made.
6. Confirm a missing, ambiguous, or non-E.164 Contact phone blocks WhatsApp and
   phone activity without allowing a typed destination.
7. Confirm provider audit records mask the number and store no bearer token.
8. Confirm the same WhatsApp request key and phone external call ID are
   idempotent, then validate the three-attempt WhatsApp failure limit.

## Metrics and limits

- Email **accepted rate** is `(Sent + Partially Sent) / (Sent + Partially Sent +
  Error)` over at most the 500 most recently modified Email Queue rows. It means
  the configured mail server accepted processing; it does not prove inbox
  delivery, message opening, or customer response.
- Pending is `Not Sent + Sending`. The workspace separately displays Error.
- WhatsApp **Accepted** means the configured adapter returned HTTP 2xx. Final
  handset delivery requires provider callbacks and is not claimed by this
  release.
- Ticket history reads at most 100 standard Communications; the app requests 50.
- Forwarding allows 20 combined To/CC recipients, 10 attachments, a 300-character
  subject, and a 100,000-character message.
- Phone summaries allow 2,000 characters and durations from 0 to 86,400 seconds.

## Rollback

Disable WhatsApp first:

```shell
bench --site <site> set-config bude_helpdesk_whatsapp_enabled 0
```

Restart web/workers, then roll back the Flutter bundle and `bude_api` commit
together. Existing tickets are not mutated beyond ordinary linked Communication,
Email Queue, File, and Integration Request records created by deliberate agent
actions. Retain those records under the site's normal audit/retention policy.
