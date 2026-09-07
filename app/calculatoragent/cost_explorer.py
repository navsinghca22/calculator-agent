"""Read-only helpers for retrieving AWS Cost Explorer data."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError


COST_EXPLORER_REGION = "us-east-1"


def get_cost_and_usage_pages(cost_explorer_client: Any, request: dict[str, Any]) -> list[dict[str, Any]]:
    """Retrieve every page returned by a Cost Explorer query."""
    response = cost_explorer_client.get_cost_and_usage(**request)
    pages = [response]
    seen_tokens: set[str] = set()

    while next_token := response.get("NextPageToken"):
        if next_token in seen_tokens:
            raise RuntimeError("Cost Explorer returned a repeated pagination token.")
        seen_tokens.add(next_token)
        response = cost_explorer_client.get_cost_and_usage(
            **request,
            NextPageToken=next_token,
        )
        pages.append(response)

    return pages


def month_to_date_reported_period(today: date) -> tuple[str, str] | None:
    """Return a complete-day current-month period suitable for Cost Explorer.

    Cost Explorer's end date is exclusive.  Excluding the current partial day
    prevents the agent from presenting an incomplete daily number as final.
    """
    start = today.replace(day=1)
    if today <= start:
        return None
    return start.isoformat(), today.isoformat()


def fetch_month_to_date_cost(
    cost_explorer_client: Any,
    *,
    today: date,
) -> dict[str, Any]:
    """Fetch unblended cost for the completed days of the current month."""
    period = month_to_date_reported_period(today)
    if period is None:
        return {
            "amount": "0",
            "currency": "USD",
            "estimated": True,
            "period_start": today.isoformat(),
            "period_end_exclusive": today.isoformat(),
            "note": "No completed days are available yet for this month.",
        }

    start, end = period
    request = {
        "TimePeriod": {"Start": start, "End": end},
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
    }

    amount = Decimal("0")
    currency = "USD"
    estimated = False
    for response in get_cost_and_usage_pages(cost_explorer_client, request):
        for result in response.get("ResultsByTime", []):
            cost = result.get("Total", {}).get("UnblendedCost", {})
            amount += Decimal(cost.get("Amount", "0"))
            currency = cost.get("Unit", currency)
            estimated = estimated or bool(result.get("Estimated", False))

    return {
        "amount": str(amount),
        "currency": currency,
        "estimated": estimated,
        "period_start": start,
        "period_end_exclusive": end,
        "note": (
            f"Includes completed days from {start} through "
            f"{(today - timedelta(days=1)).isoformat()}. "
            "The current partial day is not included."
        ),
    }


def fetch_month_to_date_cost_by_service(
    cost_explorer_client: Any,
    *,
    today: date,
) -> dict[str, Any]:
    """Fetch completed current-month cost grouped by AWS service."""
    period = month_to_date_reported_period(today)
    if period is None:
        return {
            "services": [],
            "currency": "USD",
            "estimated": True,
            "period_start": today.isoformat(),
            "period_end_exclusive": today.isoformat(),
            "note": "No completed days are available yet for this month.",
        }

    start, end = period
    request = {
        "TimePeriod": {"Start": start, "End": end},
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [{"Type": "DIMENSION", "Key": "SERVICE"}],
    }

    amounts_by_service: dict[str, Decimal] = {}
    currency = "USD"
    estimated = False
    for response in get_cost_and_usage_pages(cost_explorer_client, request):
        for result in response.get("ResultsByTime", []):
            estimated = estimated or bool(result.get("Estimated", False))
            for group in result.get("Groups", []):
                keys = group.get("Keys", [])
                service = keys[0] if keys else "Uncategorized"
                cost = group.get("Metrics", {}).get("UnblendedCost", {})
                amounts_by_service[service] = amounts_by_service.get(service, Decimal("0")) + Decimal(
                    cost.get("Amount", "0")
                )
                currency = cost.get("Unit", currency)

    services = [
        {"service": service, "amount": str(amount)}
        for service, amount in sorted(
            amounts_by_service.items(), key=lambda item: item[1], reverse=True
        )
    ]
    return {
        "services": services,
        "currency": currency,
        "estimated": estimated,
        "period_start": start,
        "period_end_exclusive": end,
        "note": (
            f"Includes completed days from {start} through "
            f"{(today - timedelta(days=1)).isoformat()}. "
            "The current partial day is not included."
        ),
    }


def get_month_to_date_cost() -> dict[str, Any]:
    """Return read-only current-month AWS cost through the last completed day."""
    try:
        client = boto3.client("ce", region_name=COST_EXPLORER_REGION)
        return fetch_month_to_date_cost(client, today=date.today())
    except (BotoCoreError, ClientError) as error:
        return {
            "error": "Unable to retrieve AWS Cost Explorer data.",
            "detail": str(error),
        }


def get_month_to_date_cost_by_service() -> dict[str, Any]:
    """Return read-only current-month AWS costs by service through the last completed day."""
    try:
        client = boto3.client("ce", region_name=COST_EXPLORER_REGION)
        return fetch_month_to_date_cost_by_service(client, today=date.today())
    except (BotoCoreError, ClientError) as error:
        return {
            "error": "Unable to retrieve AWS Cost Explorer data.",
            "detail": str(error),
        }
