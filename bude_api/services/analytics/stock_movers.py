"""Grouped analytics.stock endpoints: stock_movers."""

from ._stock_analytics_shared import *  # noqa: F401,F403

def movers(
    warehouse: str | None = None,
    days: int = 90,
    limit: int = 50,
    lead_time_days: int = 14,
    safety_stock_days: int = 7,
) -> dict:
    """Fast/slow/dead item movement insights with explainable reorder qty."""
    if frappe is None:
        return failure("Frappe not available.", code="ENV_NO_FRAPPE")

    permission_error = require_stock_execution_role(frappe)
    if permission_error:
        return permission_error

    days = _bounded_int(days, default=90, minimum=1, maximum=_MAX_RANGE_DAYS)
    limit = _bounded_int(limit, default=50, minimum=1, maximum=_MAX_LIMIT)
    lead_time_days = _bounded_int(
        lead_time_days,
        default=14,
        minimum=0,
        maximum=180,
    )
    safety_stock_days = _bounded_int(
        safety_stock_days,
        default=7,
        minimum=0,
        maximum=180,
    )
    warehouse = (warehouse or "").strip() or None
    today = _today()
    from_date = frappe.utils.add_days(today, -days)
    velocities = _movement_by_item(warehouse, from_date)
    bins = _bin_balances(warehouse, list(velocities.keys()))

    rows = []
    for item_code, qty in velocities.items():
        daily_velocity = qty / days
        actual_qty = bins.get(item_code, 0.0)
        days_of_cover = (
            None if daily_velocity <= 0 else round(actual_qty / daily_velocity, 2)
        )
        suggested_qty = max(
            0.0,
            round((daily_velocity * (lead_time_days + safety_stock_days)) - actual_qty, 2),
        )
        rows.append({
            "item_code": item_code,
            "movement_qty": round(qty, 6),
            "daily_velocity": round(daily_velocity, 6),
            "actual_qty": actual_qty,
            "days_of_cover": days_of_cover,
            "suggested_reorder_qty": suggested_qty,
            "explanation": (
                f"{round(daily_velocity, 2)} per day x "
                f"{lead_time_days + safety_stock_days} days - "
                f"{round(actual_qty, 2)} on hand"
            ),
        })

    rows.sort(key=lambda row: (-row["movement_qty"], row["item_code"]))
    fast = rows[:limit]
    slow = list(reversed(rows[-limit:])) if rows else []
    dead = _dead_items(warehouse, from_date, limit)
    return success({
        "from_date": from_date,
        "to_date": today,
        "warehouse": warehouse,
        "fast": fast,
        "slow": slow,
        "dead": dead,
        "lead_time_days": lead_time_days,
        "safety_stock_days": safety_stock_days,
    })
