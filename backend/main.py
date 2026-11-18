# from fastapi import FastAPI

# app = FastAPI(title="Expense Tracker API")


# @app.get("/")
# def home():
#     return {
#         "message": "Expense Tracker API is running!",
#         "status": "success",
#     }


# @app.get("/health")
# def health_check():
#     return {"status": "healthy"}



import calendar
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.database.db import get_connection


# Create the FastAPI application.
app = FastAPI(title="Expense Tracker API")
frontend_origins = [
    origin.strip()
    for origin in os.environ.get(
        "FRONTEND_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Define the fields required when creating or updating an expense.
class ExpenseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0, allow_inf_nan=False)
    category: str = Field(min_length=1, max_length=50)
    expense_date: date
    notes: str = Field(default="", max_length=500)


class RecurringIncomeCreate(BaseModel):
    person: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0, allow_inf_nan=False)
    frequency: Literal["monthly", "biweekly", "once"]
    income_date: date | None = None


class RecurringBillCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    amount: float = Field(gt=0, allow_inf_nan=False)
    category: str = Field(default="Bills", min_length=1, max_length=50)
    due_day: int = Field(ge=1, le=31)


def row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a database row into a JSON-friendly dictionary."""
    return {
        "id": row["id"],
        "title": row["title"],
        "amount": float(row["amount"]),
        "category": row["category"],
        "expense_date": row["expense_date"].isoformat(),
        "notes": row["notes"] or "",
        "created_at": _format_timestamp(row["created_at"]),
    }


def _format_timestamp(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    return value


def _format_date(value: date | str | None) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    return value


def _recurring_bill_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "amount": float(row["amount"]),
        "category": row["category"],
        "due_day": row["due_day"],
        "created_at": _format_timestamp(row["created_at"]),
    }


@app.get("/")
def home(request: Request):
    if "text/html" in request.headers.get("accept", ""):
        return FileResponse(
            Path(__file__).resolve().parents[1] / "frontend" / "index.html"
        )
    return {
        "message": "Expense Tracker API is running!",
        "status": "success",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


@app.get("/recurring/income")
def get_recurring_income(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
):
    start_date = date(year, month, 1)
    end_date = date(year + (month == 12), month % 12 + 1, 1)
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM recurring_income
            WHERE frequency IN ('monthly', 'biweekly')
               OR (income_date >= %s AND income_date < %s)
            ORDER BY person, id
            """,
            (start_date, end_date),
        ).fetchall()

    items = [
        {
            "id": row["id"],
            "person": row["person"],
            "source": row["source"],
            "amount": float(row["amount"]),
            "frequency": row["frequency"],
            "income_date": _format_date(row["income_date"]),
            "monthly_amount": round(
                float(row["amount"])
                * (2 if row["frequency"] == "biweekly" else 1),
                2,
            ),
        }
        for row in rows
    ]
    return {
        "items": items,
        "total_monthly": round(sum(item["monthly_amount"] for item in items), 2),
    }


@app.post("/recurring/income", status_code=status.HTTP_201_CREATED)
def create_recurring_income(income: RecurringIncomeCreate):
    person = income.person.strip()
    source = income.source.strip()
    if not person or not source:
        raise HTTPException(status_code=422, detail="Person and source cannot be blank.")
    if (income.frequency == "once") != (income.income_date is not None):
        raise HTTPException(
            status_code=422,
            detail="One-time income needs a date; recurring income must not have one.",
        )

    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO recurring_income (person, source, amount, frequency, income_date)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, person, source, amount, frequency, income_date
            """,
            (
                person,
                source,
                income.amount,
                income.frequency,
                income.income_date,
            ),
        ).fetchone()

    monthly_amount = float(row["amount"]) * (
        2 if row["frequency"] == "biweekly" else 1
    )
    return {
        "id": row["id"],
        "person": row["person"],
        "source": row["source"],
        "amount": float(row["amount"]),
        "frequency": row["frequency"],
        "income_date": _format_date(row["income_date"]),
        "monthly_amount": round(monthly_amount, 2),
    }


@app.delete("/recurring/income/{income_id}")
def delete_recurring_income(income_id: int):
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM recurring_income WHERE id = %s", (income_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Recurring income not found.")
    return {"message": "Recurring income deleted."}


@app.get("/recurring/bills")
def get_recurring_bills(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
):
    period = f"{year:04d}-{month:02d}"
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT bills.*, payments.paid_on
            FROM recurring_bills AS bills
            LEFT JOIN bill_payments AS payments
              ON payments.bill_id = bills.id AND payments.period = %s
            ORDER BY bills.due_day, bills.title
            """,
            (period,),
        ).fetchall()
        income_total = connection.execute(
            """
            SELECT COALESCE(SUM(
                amount * CASE frequency WHEN 'biweekly' THEN 2 ELSE 1 END
            ), 0) AS income_total
            FROM recurring_income
            WHERE frequency IN ('monthly', 'biweekly')
               OR (income_date >= %s AND income_date < %s)
            """,
            (start_date, end_date),
        ).fetchone()["income_total"]
        paid_total = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS paid_total
            FROM expenses
            WHERE notes = %s
            """,
            (f"Recurring bill payment ({period})",),
        ).fetchone()["paid_total"]

    items = [
        {
            "id": row["id"],
            "title": row["title"],
            "amount": float(row["amount"]),
            "category": row["category"],
            "due_day": row["due_day"],
            "paid": row["paid_on"] is not None,
            "paid_on": _format_date(row["paid_on"]),
        }
        for row in rows
    ]
    return {
        "period": period,
        "items": items,
        "income_total": round(float(income_total), 2),
        "scheduled_total": round(sum(item["amount"] for item in items), 2),
        "paid_total": round(float(paid_total), 2),
    }


@app.post("/recurring/bills", status_code=status.HTTP_201_CREATED)
def create_recurring_bill(bill: RecurringBillCreate):
    title = bill.title.strip()
    category = bill.category.strip()
    if not title or not category:
        raise HTTPException(status_code=422, detail="Bill and category cannot be blank.")

    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO recurring_bills (title, amount, category, due_day)
            VALUES (%s, %s, %s, %s)
            RETURNING id, title, amount, category, due_day, created_at
            """,
            (title, bill.amount, category, bill.due_day),
        ).fetchone()
    return _recurring_bill_to_dict(row)


@app.delete("/recurring/bills/{bill_id}")
def delete_recurring_bill(bill_id: int):
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM recurring_bills WHERE id = %s", (bill_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Recurring bill not found.")
    return {"message": "Recurring bill deleted."}


@app.post("/recurring/bills/{bill_id}/pay")
def mark_recurring_bill_paid(
    bill_id: int,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
):
    period = f"{year:04d}-{month:02d}"
    due_date = date(year, month, 1)

    with get_connection() as connection:
        bill = connection.execute(
            "SELECT * FROM recurring_bills WHERE id = %s", (bill_id,)
        ).fetchone()
        if bill is None:
            raise HTTPException(status_code=404, detail="Recurring bill not found.")

        existing = connection.execute(
            "SELECT id FROM bill_payments WHERE bill_id = %s AND period = %s",
            (bill_id, period),
        ).fetchone()
        if existing is not None:
            raise HTTPException(status_code=409, detail="This bill is already marked paid.")

        day = min(bill["due_day"], calendar.monthrange(year, month)[1])
        expense_date = due_date.replace(day=day)
        expense_id = connection.execute(
            """
            INSERT INTO expenses (title, amount, category, expense_date, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                bill["title"],
                bill["amount"],
                bill["category"],
                expense_date,
                f"Recurring bill payment ({period})",
            ),
        ).fetchone()["id"]
        connection.execute(
            """
            INSERT INTO bill_payments (bill_id, period, amount, expense_id, paid_on)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (bill_id, period, bill["amount"], expense_id, date.today()),
        )

    return {"message": "Bill marked paid.", "expense_id": expense_id, "period": period}


@app.delete("/recurring/bills/{bill_id}/pay")
def undo_recurring_bill_payment(
    bill_id: int,
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
):
    period = f"{year:04d}-{month:02d}"
    with get_connection() as connection:
        payment = connection.execute(
            "SELECT expense_id FROM bill_payments WHERE bill_id = %s AND period = %s",
            (bill_id, period),
        ).fetchone()
        if payment is None:
            raise HTTPException(status_code=404, detail="Paid bill record not found.")
        connection.execute(
            "DELETE FROM expenses WHERE id = %s", (payment["expense_id"],)
        )
    return {"message": "Bill payment undone.", "period": period}


# READ: Return all expenses.
@app.get("/expenses")
def get_expenses():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM expenses
            ORDER BY expense_date DESC, id DESC
            """
        ).fetchall()

    return [row_to_dict(row) for row in rows]

@app.get("/expenses/summary")
def get_expense_summary():
    """Return overall spending statistics."""

    with get_connection() as connection:
        row = connection.execute(
        """
        SELECT
            COUNT(*) AS expense_count,
            COALESCE(SUM(amount), 0) AS total_spent,
            COALESCE(AVG(amount), 0) AS average_expense
            FROM expenses
        """
        ).fetchone()

    return {
        "expense_count": row["expense_count"],
        "total_spent": round(float(row["total_spent"]), 2),
        "average_expense": round(float(row["average_expense"]), 2),
    }

@app.get("/expenses/categories")
def get_category_totals():
    """Return spending totals grouped by category."""

    with get_connection() as connection:
        rows = connection.execute("""
            SELECT
                category,
                COUNT(*) AS expense_count,
                SUM(amount) AS total_spent
            FROM expenses
            GROUP BY category
            ORDER BY total_spent DESC
        """).fetchall()

    return [
        {
            "category": row["category"],
            "expense_count": row["expense_count"],
            "total_spent": round(float(row["total_spent"]), 2),
        }
        for row in rows
    ]

@app.get("/expenses/summary/monthly")
def get_monthly_summary(
    year: int = Query(ge=2000, le=2100),
    month: int = Query(ge=1, le=12),
):
    """Return spending statistics for a selected month."""

    start_date = date(year, month, 1)

    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

    with get_connection() as connection:
        row = connection.execute("""
            SELECT
                COUNT(*) AS expense_count,
                COALESCE(SUM(amount), 0) AS total_spent,
                COALESCE(AVG(amount), 0) AS average_expense
            FROM expenses
            WHERE expense_date >= %s
              AND expense_date < %s
        """, (start_date, end_date)).fetchone()

        period = f"{year:04d}-{month:02d}"
        income_total = connection.execute(
            """
            SELECT COALESCE(SUM(
                amount * CASE frequency WHEN 'biweekly' THEN 2 ELSE 1 END
            ), 0) AS income_total
            FROM recurring_income
            """
        ).fetchone()["income_total"]

        paid_bills_total = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS paid_bills_total
            FROM expenses
            WHERE notes = %s
            """,
            (f"Recurring bill payment ({period})",),
        ).fetchone()["paid_bills_total"]

        other_expenses_total = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS other_expenses_total
            FROM expenses
            WHERE expense_date >= %s
              AND expense_date < %s
              AND (notes IS NULL OR notes NOT LIKE 'Recurring bill payment (%%')
            """,
            (start_date, end_date),
        ).fetchone()["other_expenses_total"]

    income_total = float(income_total)
    paid_bills_total = float(paid_bills_total)
    other_expenses_total = float(other_expenses_total)
    current_cash = income_total - paid_bills_total - other_expenses_total

    return {
        "year": year,
        "month": month,
        "expense_count": row["expense_count"],
        "total_spent": round(float(row["total_spent"]), 2),
        "average_expense": round(float(row["average_expense"]), 2),
        "income_total": round(income_total, 2),
        "paid_bills_total": round(paid_bills_total, 2),
        "other_expenses_total": round(other_expenses_total, 2),
        "current_cash": round(current_cash, 2),
    }

# CREATE: Save a new expense.
@app.post("/expenses", status_code=status.HTTP_201_CREATED)
def create_expense(expense: ExpenseCreate):
    title = expense.title.strip()
    category = expense.category.strip()

    if not title or not category:
        raise HTTPException(
            status_code=422,
            detail="Title and category cannot be blank.",
        )

    with get_connection() as connection:
        row = connection.execute(
            """
            INSERT INTO expenses
                (title, amount, category, expense_date, notes)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, title, amount, category, expense_date, notes, created_at
            """,
            (
                title,
                expense.amount,
                category,
                expense.expense_date,
                expense.notes.strip(),
            ),
        ).fetchone()

    return row_to_dict(row)


# UPDATE: Modify an existing expense.
@app.put("/expenses/{expense_id}")
def update_expense(expense_id: int, expense: ExpenseCreate):
    title = expense.title.strip()
    category = expense.category.strip()

    if not title or not category:
        raise HTTPException(
            status_code=422,
            detail="Title and category cannot be blank.",
        )

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE expenses
            SET title = %s, amount = %s, category = %s,
                expense_date = %s, notes = %s
            WHERE id = %s
            """,
            (
                title,
                expense.amount,
                category,
                expense.expense_date,
                expense.notes.strip(),
                expense_id,
            ),
        )

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Expense not found.",
            )

        row = connection.execute(
            """SELECT id, title, amount, category, expense_date, notes, created_at
            FROM expenses WHERE id = %s""",
            (expense_id,),
        ).fetchone()

    return row_to_dict(row)


# DELETE: Remove an expense.
@app.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int):
    with get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM expenses WHERE id = %s",
            (expense_id,),
        )

        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail="Expense not found.",
            )

    return {"message": "Expense deleted successfully."}


app.mount(
    "/",
    StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend", html=True),
    name="frontend",
)
