"""Shared pagination parsing for mobile API list endpoints."""

from dataclasses import dataclass

from .response import failure


@dataclass(frozen=True)
class Page:
    limit: int
    offset: int


def parse_page(
    limit,
    offset=0,
    *,
    default_limit: int = 100,
    max_limit: int = 500,
) -> Page | dict:
    try:
        parsed_limit = default_limit if limit is None else int(limit)
        parsed_offset = 0 if offset is None else int(offset)
    except (TypeError, ValueError):
        return failure(
            "Pagination limit and offset must be integers.",
            code="PAGINATION_INVALID",
        )

    if parsed_limit < 1:
        return failure("Pagination limit must be at least 1.", code="PAGINATION_INVALID")
    if parsed_offset < 0:
        return failure("Pagination offset cannot be negative.", code="PAGINATION_INVALID")
    if parsed_limit > max_limit:
        return failure(
            f"Pagination limit cannot exceed {max_limit}.",
            code="PAGINATION_LIMIT_EXCEEDED",
        )

    return Page(limit=parsed_limit, offset=parsed_offset)
