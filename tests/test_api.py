import os
import unittest
import uuid
from datetime import date
from pathlib import Path

import psycopg
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = os.environ.get("EXPENSE_TRACKER_TEST_DATABASE_URL")
TEST_WRITE_CONFIRMATION = os.environ.get("EXPENSE_TRACKER_TEST_ALLOW_WRITES")
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
else:
    configured_env = dotenv_values(PROJECT_ROOT / ".env")
    if configured_env.get("DATABASE_URL"):
        os.environ.setdefault("DATABASE_URL", configured_env["DATABASE_URL"])

from backend.database.db import get_connection, initialize_database
from backend.main import app

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None


class ApiSurfaceTests(unittest.TestCase):
    def test_existing_routes_are_registered(self):
        routes = {
            (method, route.path)
            for route in app.routes
            for method in getattr(route, "methods", set())
        }
        expected = {
            ("GET", "/"),
            ("GET", "/health"),
            ("GET", "/expenses"),
            ("POST", "/expenses"),
            ("PUT", "/expenses/{expense_id}"),
            ("DELETE", "/expenses/{expense_id}"),
            ("GET", "/expenses/summary"),
            ("GET", "/expenses/categories"),
            ("GET", "/expenses/summary/monthly"),
            ("GET", "/recurring/income"),
            ("POST", "/recurring/income"),
            ("DELETE", "/recurring/income/{income_id}"),
            ("GET", "/recurring/bills"),
            ("POST", "/recurring/bills"),
            ("DELETE", "/recurring/bills/{bill_id}"),
            ("POST", "/recurring/bills/{bill_id}/pay"),
            ("DELETE", "/recurring/bills/{bill_id}/pay"),
        }
        self.assertTrue(expected.issubset(routes))


@unittest.skipUnless(
    TEST_DATABASE_URL and TEST_WRITE_CONFIRMATION == "expense-tracker-dev",
    "Set EXPENSE_TRACKER_TEST_DATABASE_URL and "
    "EXPENSE_TRACKER_TEST_ALLOW_WRITES=expense-tracker-dev to run Neon integration tests.",
)
class NeonApiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if TestClient is None:
            raise RuntimeError("Install the test dependencies from requirements.txt.")
        initialize_database()
        cls.client = TestClient(app)
        cls.run_id = uuid.uuid4().hex[:12]

    def test_health_and_frontend_assets(self):
        self.assertEqual(self.client.get("/").json()["status"], "success")
        self.assertEqual(self.client.get("/health").json(), {"status": "healthy"})
        browser_page = self.client.get("/", headers={"accept": "text/html"})
        self.assertEqual(browser_page.status_code, 200)
        self.assertIn("Expense Tracker", browser_page.text)
        page = self.client.get("/index.html")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Expense Tracker", page.text)
        self.assertEqual(self.client.get("/script.js").status_code, 200)

    def test_expense_crud_and_reports(self):
        baseline_summary = self.client.get("/expenses/summary").json()
        baseline_monthly = self.client.get(
            "/expenses/summary/monthly?year=2026&month=3"
        ).json()
        response = self.client.post(
            "/expenses",
            json={
                "title": f"test expense {self.run_id}",
                "amount": 12.34,
                "category": f"test-{self.run_id}",
                "expense_date": "2026-03-15",
                "notes": "integration test",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        expense = response.json()
        expense_id = expense["id"]
        self.assertEqual(expense["amount"], 12.34)
        self.assertEqual(expense["expense_date"], "2026-03-15")

        updated = self.client.put(
            f"/expenses/{expense_id}",
            json={
                "title": f"updated expense {self.run_id}",
                "amount": 20.25,
                "category": f"updated-{self.run_id}",
                "expense_date": "2026-03-16",
                "notes": "updated",
            },
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["amount"], 20.25)
        self.assertEqual(updated.json()["expense_date"], "2026-03-16")

        summary = self.client.get("/expenses/summary").json()
        self.assertIn("expense_count", summary)
        categories = self.client.get("/expenses/categories").json()
        matching_category = next(
            item for item in categories if item["category"] == f"updated-{self.run_id}"
        )
        self.assertEqual(matching_category["total_spent"], 20.25)

        monthly = self.client.get(
            "/expenses/summary/monthly?year=2026&month=3"
        ).json()
        self.assertAlmostEqual(
            monthly["total_spent"], baseline_monthly["total_spent"] + 20.25
        )
        self.assertAlmostEqual(
            monthly["current_cash"], baseline_monthly["current_cash"] - 20.25
        )
        self.assertIn("current_cash", monthly)
        self.assertAlmostEqual(
            summary["total_spent"], baseline_summary["total_spent"] + 20.25
        )

        expenses = self.client.get("/expenses").json()
        self.assertTrue(any(row["id"] == expense_id for row in expenses))
        deleted = self.client.delete(f"/expenses/{expense_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        missing = self.client.delete(f"/expenses/{expense_id}")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(
            self.client.get("/expenses/summary").json(), baseline_summary
        )

    def test_recurring_income_and_one_time_income(self):
        recurring = self.client.post(
            "/recurring/income",
            json={
                "person": f"test-{self.run_id}",
                "source": "monthly",
                "amount": 100.25,
                "frequency": "monthly",
                "income_date": None,
            },
        )
        self.assertEqual(recurring.status_code, 201, recurring.text)
        recurring_id = recurring.json()["id"]

        biweekly = self.client.post(
            "/recurring/income",
            json={
                "person": f"test-{self.run_id}",
                "source": "biweekly",
                "amount": 50.25,
                "frequency": "biweekly",
                "income_date": None,
            },
        )
        self.assertEqual(biweekly.status_code, 201, biweekly.text)
        biweekly_id = biweekly.json()["id"]
        self.assertEqual(biweekly.json()["monthly_amount"], 100.5)

        one_time = self.client.post(
            "/recurring/income",
            json={
                "person": f"test-{self.run_id}",
                "source": "one-time",
                "amount": 55.50,
                "frequency": "once",
                "income_date": "2026-03-12",
            },
        )
        self.assertEqual(one_time.status_code, 201, one_time.text)
        one_time_id = one_time.json()["id"]

        listing = self.client.get(
            "/recurring/income?year=2026&month=3"
        ).json()
        matching_ids = {item["id"] for item in listing["items"]}
        self.assertIn(recurring_id, matching_ids)
        self.assertIn(biweekly_id, matching_ids)
        self.assertIn(one_time_id, matching_ids)
        self.assertEqual(one_time.json()["income_date"], "2026-03-12")

        invalid_recurring_date = self.client.post(
            "/recurring/income",
            json={
                "person": "invalid",
                "source": "monthly",
                "amount": 10,
                "frequency": "monthly",
                "income_date": "2026-03-12",
            },
        )
        self.assertEqual(invalid_recurring_date.status_code, 422)

        invalid_once = self.client.post(
            "/recurring/income",
            json={
                "person": "invalid",
                "source": "one-time",
                "amount": 10,
                "frequency": "once",
                "income_date": None,
            },
        )
        self.assertEqual(invalid_once.status_code, 422)

        for income_id in (recurring_id, biweekly_id, one_time_id):
            self.assertEqual(
                self.client.delete(f"/recurring/income/{income_id}").status_code,
                200,
            )

    def test_bill_payment_undo_constraints_and_rollback(self):
        created = self.client.post(
            "/recurring/bills",
            json={
                "title": f"test bill {self.run_id}",
                "amount": 75.25,
                "category": "Bills",
                "due_day": 31,
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        bill_id = created.json()["id"]

        paid = self.client.post(
            f"/recurring/bills/{bill_id}/pay?year=2026&month=2"
        )
        self.assertEqual(paid.status_code, 200, paid.text)
        expense_id = paid.json()["expense_id"]
        expenses = self.client.get("/expenses").json()
        payment_expense = next(row for row in expenses if row["id"] == expense_id)
        self.assertEqual(payment_expense["expense_date"], "2026-02-28")

        bill_listing = self.client.get(
            "/recurring/bills?year=2026&month=2"
        ).json()
        paid_bill = next(item for item in bill_listing["items"] if item["id"] == bill_id)
        self.assertTrue(paid_bill["paid"])

        duplicate = self.client.post(
            f"/recurring/bills/{bill_id}/pay?year=2026&month=2"
        )
        self.assertEqual(duplicate.status_code, 409)

        undone = self.client.delete(
            f"/recurring/bills/{bill_id}/pay?year=2026&month=2"
        )
        self.assertEqual(undone.status_code, 200, undone.text)
        self.assertFalse(
            any(row["id"] == expense_id for row in self.client.get("/expenses").json())
        )
        with get_connection() as connection:
            payment = connection.execute(
                "SELECT id FROM bill_payments WHERE expense_id = %s",
                (expense_id,),
            ).fetchone()
        self.assertIsNone(payment)

        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with get_connection() as connection:
                orphan_expense_id = connection.execute(
                    """
                    INSERT INTO expenses
                        (title, amount, category, expense_date, notes)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        f"rollback {self.run_id}",
                        1,
                        "test",
                        date(2026, 2, 1),
                        "",
                    ),
                ).fetchone()["id"]
                connection.execute(
                    """
                    INSERT INTO bill_payments
                        (bill_id, period, amount, expense_id, paid_on)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (bill_id + 10_000_000, "2026-02", 1, orphan_expense_id, date.today()),
                )

        with get_connection() as connection:
            rolled_back = connection.execute(
                "SELECT id FROM expenses WHERE title = %s",
                (f"rollback {self.run_id}",),
            ).fetchone()
        self.assertIsNone(rolled_back)

        deleted = self.client.delete(f"/recurring/bills/{bill_id}")
        self.assertEqual(deleted.status_code, 200, deleted.text)


if __name__ == "__main__":
    unittest.main()
