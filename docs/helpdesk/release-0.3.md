# Bude Helpdesk 0.3 release runbook

Release: `0.3.0+202608051`

Scope: Setup Health and customer activation

Target: migrated Helpdesk on Frappe 15 or 16

## What ships

- `bude_api.api.helpdesk.setup_health`, a read-only endpoint limited to
  `Agent Manager`, `System Manager`, and `Administrator`;
- a manager-only `/admin/setup` Flutter route, available from Settings, the
  drawer, and the desktop navigation rail;
- preflight checks with upstream Desk/Helpdesk handoff links;
- aggregate customer invitation/first-login activation metrics;
- an observed end-to-end launch checklist for portal access, intake,
  assignment, and outbound reply delivery.

The endpoint does not return customer names, contact details, credentials, or
configuration values. It does not send invitations or create test tickets.
Those actions remain explicit in upstream Helpdesk.

## Deploy

1. Back up the site and retain an off-site copy.
2. Deploy `bude_api`, run the normal bench dependency install, then
   `bench --site <site> migrate`.
3. Confirm the site scheduler is enabled.
4. Publish the Android APK/Web bundle and install version `0.3.0`.
5. Sign in as an Agent Manager and open Settings → Setup health.

## Smoke test

1. Confirm a plain `Agent` or customer is redirected away from `/admin/setup`.
2. Confirm the manager report contains no email address, token, key, password,
   or service-account content.
3. Resolve every blocking check; manually verify the backup warning.
4. Invite one customer from Helpdesk Customers with the `HD Customer` role.
5. Have that customer set a password, log in, and submit a real pilot ticket.
6. Assign the ticket, reply, confirm customer delivery and portal visibility,
   then refresh Setup Health until all four launch-test steps are complete.
7. Record time-to-first-ticket and the activation numerator/denominator for the
   pilot review. The commercial target is at least 70% activation.

## Rollback

The change adds no DocType, patch, scheduled task, or persistent diagnostic
state. Roll back the Flutter bundle and the `bude_api` commit together, restart
the bench workers/web processes, and clear caches. Existing Helpdesk tickets,
memberships, users, email accounts, SLAs, and invitations remain unchanged.

## Known operational notes

- The activation scan is capped at 500 customer memberships and reports when
  truncated. A paginated analytics implementation belongs in a later release.
- Activation means an enabled portal-role user has a non-empty `last_login`;
  it is not a session-frequency or engagement metric.
- Backup readiness is intentionally a manual warning because application-level
  state cannot prove that an off-site backup is recent and restorable.
- FCM is optional. Missing server credentials do not block an email/portal
  launch.
