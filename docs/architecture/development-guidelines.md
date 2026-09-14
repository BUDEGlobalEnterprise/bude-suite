# Development Guidelines

## Branching

- `main` — always deployable.
- `feat/<short-name>` for features.
- `fix/<short-name>` for bug fixes.
- One PR = one logical change. Squash-merge.

## Commit messages

Conventional Commits:

```
feat(inventory): add item search by barcode
fix(auth): refresh token before each call
chore(ci): bump flutter version in workflow
```

## Code rules (mobile)

- Run `flutter analyze` and `flutter test` before pushing.
- No `print` — use `appLogger`.
- `domain/` files must not import `package:flutter/*` or `package:dio/*`.
- DTOs in `data/` are separate types from entities in `domain/` — map between them in the repository.
- Use `Either<Failure, T>` (`dartz`) for fallible operations. Throwing is reserved for programmer errors.

## Code rules (backend / `bude_api`)

- Never create or modify DocTypes. If a feature seems to need one, raise it for review first.
- All public endpoints are explicitly decorated with `@frappe.whitelist()`; default `allow_guest=False`.
- Standard response envelope: `utils.response.success(...)` / `utils.response.failure(...)`.
- Type-hint everything. Run `ruff` and `mypy` in CI.

## Testing

- Unit tests for use cases (`domain`) and repositories (`data`) — mock the API client.
- Widget tests for non-trivial screens.
- Backend: pytest, with Frappe stubbed for unit tests; integration tests run inside a real bench.

## Secrets

- No secrets in the repo. `.env.example` lives in git; `.env` does not.
- Frappe credentials read from `site_config.json` on the server.
