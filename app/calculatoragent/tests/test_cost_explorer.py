from datetime import date
import unittest
from unittest.mock import Mock

from cost_explorer import (
    fetch_month_to_date_cost,
    fetch_month_to_date_cost_by_service,
    month_to_date_reported_period,
)


class CostExplorerTests(unittest.TestCase):
    def test_reported_period_excludes_the_current_partial_day(self):
        self.assertEqual(
            month_to_date_reported_period(date(2026, 9, 3)),
            ("2026-09-01", "2026-09-03"),
        )

    def test_reported_period_is_empty_on_the_first_day_of_the_month(self):
        self.assertIsNone(month_to_date_reported_period(date(2026, 9, 1)))

    def test_fetch_month_to_date_cost_sums_daily_results_and_marks_estimates(self):
        client = Mock()
        client.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "Total": {"UnblendedCost": {"Amount": "1.20", "Unit": "USD"}},
                    "Estimated": False,
                },
                {
                    "Total": {"UnblendedCost": {"Amount": "0.38", "Unit": "USD"}},
                    "Estimated": True,
                },
            ]
        }

        result = fetch_month_to_date_cost(client, today=date(2026, 9, 3))

        self.assertEqual(result["amount"], "1.58")
        self.assertEqual(result["currency"], "USD")
        self.assertTrue(result["estimated"])
        self.assertEqual(result["period_start"], "2026-09-01")
        self.assertEqual(result["period_end_exclusive"], "2026-09-03")
        client.get_cost_and_usage.assert_called_once_with(
            TimePeriod={"Start": "2026-09-01", "End": "2026-09-03"},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
        )

    def test_fetch_month_to_date_cost_by_service_sums_and_sorts_services(self):
        client = Mock()
        client.get_cost_and_usage.return_value = {
            "ResultsByTime": [
                {
                    "Groups": [
                        {
                            "Keys": ["Amazon Bedrock"],
                            "Metrics": {"UnblendedCost": {"Amount": "0.15", "Unit": "USD"}},
                        },
                        {
                            "Keys": ["Amazon S3"],
                            "Metrics": {"UnblendedCost": {"Amount": "0.08", "Unit": "USD"}},
                        },
                    ],
                    "Estimated": False,
                },
                {
                    "Groups": [
                        {
                            "Keys": ["Amazon Bedrock"],
                            "Metrics": {"UnblendedCost": {"Amount": "0.20", "Unit": "USD"}},
                        }
                    ],
                    "Estimated": True,
                },
            ]
        }

        result = fetch_month_to_date_cost_by_service(client, today=date(2026, 9, 3))

        self.assertEqual(
            result["services"],
            [
                {"service": "Amazon Bedrock", "amount": "0.35"},
                {"service": "Amazon S3", "amount": "0.08"},
            ],
        )
        self.assertTrue(result["estimated"])
        client.get_cost_and_usage.assert_called_once_with(
            TimePeriod={"Start": "2026-09-01", "End": "2026-09-03"},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
