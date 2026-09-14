# API Standards

## Transport

- HTTPS only in non-dev environments.
- JSON request and response bodies.
- UTF-8.

## Authentication

- Frappe token auth: `Authorization: token <api_key>:<api_secret>`.
- Session cookies are supported but not used by the mobile client.

## Endpoints used by the mobile client

### Built-in Frappe / ERPNext

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/method/login` | Username + password login |
| POST | `/api/method/logout` | End session |
| GET  | `/api/resource/<DocType>` | List standard DocType records |
| GET  | `/api/resource/<DocType>/<name>` | Fetch one record |
| POST | `/api/resource/<DocType>` | Create record |
| PUT  | `/api/resource/<DocType>/<name>` | Update record |

### Custom (`bude_api`)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET  | `/api/method/bude_api.api.health.ping` | guest | Connectivity check |
| GET  | `/api/method/bude_api.api.helpdesk.support_pulse` | Agent / Agent Manager | Permission-scoped SLA risk, workload metrics, and next-work queue |

The complete public facade is defined in the corresponding modules under
`backend/bude_api/bude_api/api/`; this table records stable integration entry
points and is expanded as product releases are documented.

## Response envelope (custom endpoints)

```json
{ "ok": true,  "data": { ... }, "message": null }
{ "ok": false, "data": null,    "message": "human-readable", "code": "MACHINE_CODE" }
```

ERPNext native endpoints keep their own envelope — do not wrap them.

## Errors

- `4xx` — client problem; do not retry without changes.
- `5xx` — server problem; client may retry with exponential backoff.
- All `4xx`/`5xx` responses include a JSON body with `message`.

## Pagination

- `limit_start`, `limit_page_length` query params on Frappe `resource` endpoints.
- Custom list endpoints follow the same names.

## Versioning

- Custom endpoints are namespaced under `bude_api.api.*`.
- Breaking changes get a new namespace (`bude_api.api_v2.*`); old paths stay alive for one release.
