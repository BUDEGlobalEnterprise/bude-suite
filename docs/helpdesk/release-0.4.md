# Bude Helpdesk 0.4 release runbook

Release: `0.4.0+202608052`

Scope: Automation and escalation pack

Target: migrated Helpdesk on Frappe 15 or 16

## What ships

- six escalation policies: unassigned age, SLA due soon, SLA breach, inactivity,
  VIP/critical, and repeated resolved-to-open transitions;
- a daily manager digest when current matches exist;
- standard Frappe `Notification Log` delivery records and `Integration Request`
  audit/retry records, with deterministic event keys and at most three attempts;
- a scheduled bounded scan at minutes 7, 22, 37, and 52 of each hour;
- manager-only status, dry-run, live-run, and retry endpoints;
- an English/Arabic `/admin/automation` workspace with delivery metrics, policy
  thresholds, preview results, and recent audit events.

No custom DocType or schema migration is added. Automation is disabled by
default, and a deployment that does not opt in sends no automation
notifications.

## Configuration

Enable only after a successful dry run:

```shell
bench --site <site> set-config bude_helpdesk_automation_enabled 1
```

Optional site configuration keys and defaults:

| Key | Default | Allowed behavior |
| --- | ---: | --- |
| `bude_helpdesk_unassigned_minutes` | 30 | Clamped to 5-1440 minutes |
| `bude_helpdesk_due_soon_hours` | 4 | Clamped to 1-24 hours |
| `bude_helpdesk_inactivity_hours` | 24 | Clamped to 1-720 hours |
| `bude_helpdesk_reopen_count` | 2 | Clamped to 1-20 transitions |
| `bude_helpdesk_vip_customers` | empty | Comma-separated customer names |
| `bude_helpdesk_vip_priorities` | `Urgent` | Comma-separated priority names |

Example:

```shell
bench --site <site> set-config bude_helpdesk_unassigned_minutes 45
bench --site <site> set-config bude_helpdesk_vip_customers "Acme,Northwind"
```

Manager recipients are enabled users with `Agent Manager` or `System Manager`.
Ticket policies notify assigned users and fall back to managers when a ticket
has no assignee. Unassigned and digest events go to managers.

## Deploy and activate

1. Back up the site and retain an off-site copy.
2. Deploy `bude_api`, install normal bench dependencies, and run
   `bench --site <site> migrate` so scheduler hooks are refreshed.
3. Restart web, scheduler, and worker processes; confirm the scheduler is active.
4. Publish the Android APK/Web bundle and install version `0.4.0`.
5. Sign in as an Agent Manager and open Automation & escalation.
6. Leave automation disabled and select **Preview matches**. Review matches,
   assignment coverage, SLA dates, VIP configuration, and manager membership.
7. Set `bude_helpdesk_automation_enabled` to `1`, restart workers, refresh the
   workspace, and use **Run now** once for a controlled pilot.
8. Confirm in-app Notification Logs, optional FCM delivery, Integration Request
   audit rows, and the target ticket routes before relying on the schedule.

## Smoke test

1. Confirm a customer and plain Agent are redirected away from
   `/admin/automation` and receive permission errors from all three endpoints.
2. With the flag absent or false, confirm preview works while Run now and Retry
   failures remain disabled and the scheduler creates no records.
3. Prepare one test ticket for each configured policy, preview it, enable the
   engine, and run once.
4. Confirm assigned-ticket alerts route to Support Pulse and digests route to
   Automation & escalation.
5. Run again in the same event state and confirm completed audit events are
   skipped rather than delivered twice.
6. Resolve a ticket, then verify failed retries skip closed work.
7. Review delivery health after the next scheduled pass and record the success
   rate plus manual-chase baseline for the pilot.

## Metrics and limits

- **Attempted** is the number of sampled audit rows whose state is Completed or
  Failed. **Success rate** is Completed / Attempted, rounded to a percentage.
- Metrics sample the 500 most recently modified automation audit rows and show
  when that sample is full; this is an operational indicator, not an unlimited
  historical report.
- Each evaluation reads at most 501 open tickets and processes the first 500 in
  creation order. The response reports truncation when more work exists.
- Preview results expose at most 100 event-recipient matches. Delivery still
  evaluates the bounded ticket set.
- Reopen detection reads standard `HD Ticket Activity` status changes. The
  policy reports unavailable when that DocType is absent.
- FCM fan-out is best effort. Notification Log and Integration Request records
  remain the source of truth when push credentials or devices are unavailable.

## Rollback

Disable delivery first:

```shell
bench --site <site> set-config bude_helpdesk_automation_enabled 0
```

Restart scheduler/workers, then roll back the Flutter bundle and `bude_api`
commit together. Existing tickets are never mutated by this release. Existing
Notification Log and Integration Request audit records may be retained for
evidence or archived under the site's normal retention process; do not delete
them as part of an application rollback.
