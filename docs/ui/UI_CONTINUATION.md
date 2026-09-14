# UI continuation handoff

Last updated: 2026-08-12

## Start here before changing backend UI

1. Pull the latest `main` branch and confirm the Bude UI checkpoint is present.
2. Do not replace the Frappe theme files or hook entries. Extend them through the
   existing variables and component rules:
   - `backend/bude_api/bude_api/public/css/bude_theme.css`
   - `backend/bude_api/bude_api/public/css/bude_web_theme.css`
   - `backend/bude_api/bude_api/hooks.py`
3. Run the backend branding and health tests before and after backend UI work:

   ```bash
   backend/bude_api/.venv/bin/pytest -q \
     backend/bude_api/bude_api/tests/test_branding.py \
     backend/bude_api/bude_api/tests/test_health.py
   ```

4. On a Frappe bench, rebuild assets and clear the cache after CSS changes:

   ```bash
   bench build --app bude_api
   bench clear-cache
   ```

## Current UI foundation

- Company name: **Bude Global Enterprises**.
- Shared Flutter layout primitives live in
  `mobile-app/access_control/lib/src/ui/bude_layout.dart`.
- Colors, typography, cards, fields, buttons, navigation, sheets, dialogs, and
  light/dark behavior are centralized in each Flutter app's `core/theme` files.
- The design rules are documented in `shared/branding/DESIGN_SYSTEM.md`.
- The extended reference gallery is generated from
  `mobile-app/tools/screenshotter/mock-suite.html`.
- Live screens use signed-in Frappe users and actual ERP records. The South
  Indian names in the screenshot gallery are fictional presentation fixtures,
  not production data.

## Functional layouts already migrated

- Inventory: dashboard, stock catalogue, analytics, reports, assets, warehouses,
  and settings; scan, transfer, and cycle-count flows retain their operational
  components and real queue logic.
- HR: dashboard, attendance, leave, manager summary, notifications, profile,
  expenses, requests, shift roster, salary, and settings.
- Sales: dashboard, customers, customer 360, field day, visits, manager tools,
  CRM workspaces, new order/cart, collections, setup doctor, and settings.
- Helpdesk: support pulse, ticket list/detail, new ticket, agent queue, channels,
  automation, setup health, and settings.
- Frappe Desk and web pages: shared Bude theme and company branding through app
  hooks.

The migrated pages keep their real providers, navigation, searches, filters,
refresh actions, validations, offline queues, submissions, uploads, approvals,
and payment actions. Do not replace them with hard-coded mock data.

## Accessibility and responsive guardrails

- Shared layout tests cover a 320 px phone, 1.6x text, RTL, tablet, dark mode,
  and Android minimum tap targets.
- Every app-local `AppCard`/`AppListItem` copy has the same narrow RTL,
  large-text, dark-mode, and tap-target contract.
- Representative production screens cover the same matrix in Inventory
  analytics, HR settings, Sales customer 360, and Helpdesk setup health.
- Metric and quick-action grids grow with text scale; card title actions stack
  when narrow; HR preference controls and Sales customer actions/metadata adapt
  without horizontal overflow.
- Shared metric and quick-action cards expose enabled-button semantics when
  interactive; quick actions have a keyboard focus-order regression test.
- Tappable app-local cards expose the same enabled-button role in every app;
  `AppListItem` semantics are guarded through the underlying `ListTile`.
- Confirmation dialogs in HR, Sales, and Helpdesk guard Cancel-to-Confirm Tab
  order, closed-loop focus containment, accessible labels, and button roles.
- Inventory scan exception controls guard segmented selected-state semantics,
  the full seven-step modal Tab cycle, and Save/final-use submission actions.

## Recommended next round

1. Compare real-device phone and tablet captures with `mobile-app/screenshots/`.
2. Extend screen-reader coverage to quantity controls, validation/live-region
   announcements, sortable tables, and compound list-row actions.
3. Add stable light/dark visual snapshots for one representative screen per
   app after device comparison signs off the spacing.
4. Keep controls functional and fed by repositories; use fixture names only in
   screenshot generation and tests.

## Validation at this checkpoint

- Backend branding and health tests: 8 passed.
- Changed Dart sources: delimiter/static structure check passed.
- Frappe CSS: balanced rules check passed.
- Git whitespace check: passed.
- Flutter analysis: no issues in the shared access-control package, Inventory,
  Sales, Helpdesk, or HR.
- Flutter tests: 766 passed across access control (21), Inventory (407), Sales
  (54), Helpdesk (118), and HR (166). Use `flutter test --concurrency=2` on
  memory-constrained Windows hosts.
