
const isLocalFrontend =
    ["localhost", "127.0.0.1"].includes(window.location.hostname) &&
    window.location.port === "5500";
const API_URL = window.EXPENSE_TRACKER_API_URL ||
    (isLocalFrontend ? "http://127.0.0.1:8001" : "");

// Find the HTML elements we'll update.
const summaryYear = document.getElementById("summary-year");
const summaryMonth = document.getElementById("summary-month");
const summaryStatus = document.getElementById("summary-status");
const totalSpent = document.getElementById("total-spent");
const expenseCount = document.getElementById("expense-count");
const averageExpense = document.getElementById("average-expense");
const currentCash = document.getElementById("current-cash");
const expenseList = document.getElementById("expense-list");
const expenseListStatus = document.getElementById("expense-list-status");
const categoryTotals = document.getElementById("category-totals");
const expenseForm = document.getElementById("expense-form");
const formStatus = document.getElementById("form-status");
const themeToggle = document.getElementById("theme-toggle");
const incomeForm = document.getElementById("income-form");
const billForm = document.getElementById("bill-form");
const incomeList = document.getElementById("income-list");
const billList = document.getElementById("bill-list");
const recurringStatus = document.getElementById("recurring-status");
const monthlyIncome = document.getElementById("monthly-income");
const scheduledBills = document.getElementById("scheduled-bills");
const paidBills = document.getElementById("paid-bills");
const incomeAfterBills = document.getElementById("income-after-bills");
const incomeFrequency = document.getElementById("income-frequency");
const incomeDateField = document.getElementById("income-date-field");
const incomeDate = document.getElementById("income-date");

function setTheme(theme) {
    const activeTheme = theme === "light" ? "light" : "dark";
    const nextTheme = activeTheme === "dark" ? "light" : "dark";

    document.documentElement.dataset.theme = activeTheme;
    themeToggle.textContent = `Use ${nextTheme} theme`;
    localStorage.setItem("expense-tracker-theme", activeTheme);
}

setTheme(localStorage.getItem("expense-tracker-theme") || "dark");
themeToggle.addEventListener("click", () => {
    const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
});

// Format numbers as US dollars.
function formatMoney(amount) {
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD"
    }).format(Number(amount) || 0);
}

// Display a status message.
function showStatus(element, message, type = "") {
    element.textContent = message;
    element.className = `status ${type}`.trim();
}

// Load the summary for the selected month.
async function loadMonthlySummary() {
    const year = Number(summaryYear.value);
    const month = Number(summaryMonth.value);

    if (!Number.isInteger(year) || year < 2000 || year > 2100) {
        showStatus(summaryStatus, "Enter a year between 2000 and 2100.", "error");
        return;
    }

    showStatus(summaryStatus, "Loading monthly summary...");

    try {
        const response = await fetch(
            `${API_URL}/expenses/summary/monthly?year=${year}&month=${month}`
        );

        if (!response.ok) {
            throw new Error(`Request failed: ${response.status}`);
        }

        const data = await response.json();

        totalSpent.textContent = formatMoney(data.total_spent);
        expenseCount.textContent = data.expense_count;
        averageExpense.textContent = formatMoney(data.average_expense);
        currentCash.textContent = formatMoney(data.current_cash);
        currentCash.className = data.current_cash > 0
            ? "cash-positive"
            : data.current_cash < 0
                ? "cash-negative"
                : "cash-neutral";

        showStatus(summaryStatus, `Summary loaded for ${month}/${year}.`, "success");
    } catch (error) {
        console.error("Monthly summary error:", error);
        showStatus(
            summaryStatus,
            "Could not load summary. Make sure the API is running.",
            "error"
        );
    }
}

// Load all expenses and display them in the table.
async function loadExpenses() {
    try {
        const response = await fetch(`${API_URL}/expenses`);

        if (!response.ok) {
            throw new Error(`Request failed: ${response.status}`);
        }

        const expenses = await response.json();
        expenseList.replaceChildren();

        if (expenses.length === 0) {
            const row = document.createElement("tr");
            const cell = document.createElement("td");
            cell.colSpan = 5;
            cell.textContent = "No expenses recorded yet.";
            row.appendChild(cell);
            expenseList.appendChild(row);
            return;
        }

        for (const expense of expenses) {
            const row = document.createElement("tr");

            const dateCell = document.createElement("td");
            dateCell.textContent = expense.expense_date;

            const titleCell = document.createElement("td");
            titleCell.textContent = expense.title;

            const categoryCell = document.createElement("td");
            categoryCell.textContent = expense.category;

            const amountCell = document.createElement("td");
            amountCell.textContent = formatMoney(expense.amount);

            const actionCell = document.createElement("td");
            const deleteButton = document.createElement("button");
            deleteButton.type = "button";
            deleteButton.className = "delete-button";
            deleteButton.textContent = "Delete";
            deleteButton.setAttribute("aria-label", `Delete expense: ${expense.title}`);
            deleteButton.addEventListener("click", () => {
                deleteExpense(expense.id, expense.title, deleteButton);
            });
            actionCell.appendChild(deleteButton);

            row.append(dateCell, titleCell, categoryCell, amountCell, actionCell);
            expenseList.appendChild(row);
        }
    } catch (error) {
        console.error("Expense list error:", error);
        expenseList.replaceChildren();

        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 5;
        cell.textContent = "Could not load expenses. Check that the API is running.";
        row.appendChild(cell);
        expenseList.appendChild(row);
    }
}

async function loadRecurringIncome() {
    const year = Number(summaryYear.value);
    const month = Number(summaryMonth.value);
    const response = await fetch(
        `${API_URL}/recurring/income?year=${year}&month=${month}`
    );
    if (!response.ok) {
        throw new Error(`Could not load income: ${response.status}`);
    }

    const data = await response.json();
    monthlyIncome.textContent = formatMoney(data.total_monthly);
    incomeList.replaceChildren();

    if (data.items.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 5;
        cell.textContent = "No income entries for this month.";
        row.appendChild(cell);
        incomeList.appendChild(row);
        return;
    }

    for (const item of data.items) {
        const row = document.createElement("tr");
        const person = document.createElement("td");
        person.textContent = item.person;
        const source = document.createElement("td");
        source.textContent = item.source;
        const pay = document.createElement("td");
        const frequencyLabel = item.frequency === "biweekly"
            ? "check"
            : item.frequency === "once"
                ? `one-time (${item.income_date})`
                : "month";
        pay.textContent = `${formatMoney(item.amount)} / ${frequencyLabel}`;
        const monthly = document.createElement("td");
        monthly.textContent = formatMoney(item.monthly_amount);
        const action = document.createElement("td");
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "delete-button compact-button";
        remove.textContent = "Remove";
        remove.setAttribute("aria-label", `Remove ${item.source} income for ${item.person}`);
        remove.addEventListener("click", () => deleteRecurringIncome(item.id));
        action.appendChild(remove);
        row.append(person, source, pay, monthly, action);
        incomeList.appendChild(row);
    }
}

async function loadRecurringBills() {
    const year = Number(summaryYear.value);
    const month = Number(summaryMonth.value);
    const response = await fetch(
        `${API_URL}/recurring/bills?year=${year}&month=${month}`
    );
    if (!response.ok) {
        throw new Error(`Could not load bills: ${response.status}`);
    }

    const data = await response.json();
    scheduledBills.textContent = formatMoney(data.scheduled_total);
    paidBills.textContent = formatMoney(data.paid_total);
    incomeAfterBills.textContent = formatMoney(data.income_total - data.paid_total);
    billList.replaceChildren();

    if (data.items.length === 0) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 5;
        cell.textContent = "No recurring bills added.";
        row.appendChild(cell);
        billList.appendChild(row);
        return;
    }

    for (const bill of data.items) {
        const row = document.createElement("tr");
        const title = document.createElement("td");
        title.textContent = bill.title;
        const due = document.createElement("td");
        due.textContent = `Day ${bill.due_day}`;
        const amount = document.createElement("td");
        amount.textContent = formatMoney(bill.amount);
        const state = document.createElement("td");
        state.textContent = bill.paid ? `Paid ${bill.paid_on}` : "Due";
        const action = document.createElement("td");
        const paymentButton = document.createElement("button");
        paymentButton.type = "button";
        paymentButton.className = bill.paid ? "secondary-button compact-button" : "compact-button";
        paymentButton.textContent = bill.paid ? "Undo" : "Mark paid";
        paymentButton.setAttribute(
            "aria-label",
            `${bill.paid ? "Undo payment for" : "Mark paid"} ${bill.title}`
        );
        paymentButton.addEventListener("click", () => toggleBillPayment(bill));
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "delete-button compact-button";
        remove.textContent = "Remove";
        remove.setAttribute("aria-label", `Remove recurring bill ${bill.title}`);
        remove.addEventListener("click", () => deleteRecurringBill(bill.id));
        action.append(paymentButton, remove);
        row.append(title, due, amount, state, action);
        billList.appendChild(row);
    }
}

async function loadRecurringPlan() {
    try {
        await Promise.all([loadRecurringIncome(), loadRecurringBills()]);
        showStatus(recurringStatus, "Recurring plan updated.");
        return true;
    } catch (error) {
        console.error("Recurring plan error:", error);
        showStatus(recurringStatus, error.message, "error");
        return false;
    }
}

async function deleteRecurringIncome(incomeId) {
    const response = await fetch(`${API_URL}/recurring/income/${incomeId}`, {
        method: "DELETE"
    });
    if (!response.ok) {
        showStatus(recurringStatus, "Could not remove recurring income.", "error");
        return;
    }
    await loadRecurringPlan();
}

async function deleteRecurringBill(billId) {
    const response = await fetch(`${API_URL}/recurring/bills/${billId}`, {
        method: "DELETE"
    });
    if (!response.ok) {
        showStatus(recurringStatus, "Could not remove recurring bill.", "error");
        return;
    }
    await Promise.all([loadRecurringPlan(), loadMonthlySummary(), loadExpenses(), loadCategoryTotals()]);
}

async function toggleBillPayment(bill) {
    const year = Number(summaryYear.value);
    const month = Number(summaryMonth.value);
    const method = bill.paid ? "DELETE" : "POST";
    const response = await fetch(
        `${API_URL}/recurring/bills/${bill.id}/pay?year=${year}&month=${month}`,
        { method }
    );
    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        showStatus(recurringStatus, error.detail || "Could not update bill payment.", "error");
        return;
    }

    showStatus(recurringStatus, bill.paid ? `${bill.title} payment undone.` : `${bill.title} marked paid.`, "success");
    await Promise.all([
        loadRecurringPlan(),
        loadMonthlySummary(),
        loadExpenses(),
        loadCategoryTotals()
    ]);
}

async function deleteExpense(expenseId, title, button) {
    if (!window.confirm(`Delete "${title}"? This cannot be undone.`)) {
        return;
    }

    button.disabled = true;
    showStatus(expenseListStatus, `Deleting "${title}"...`);

    try {
        const response = await fetch(`${API_URL}/expenses/${expenseId}`, {
            method: "DELETE"
        });

        if (!response.ok) {
            throw new Error(`Request failed: ${response.status}`);
        }

        showStatus(expenseListStatus, `Deleted "${title}".`, "success");
        await Promise.all([
            loadMonthlySummary(),
            loadExpenses(),
            loadCategoryTotals()
        ]);
    } catch (error) {
        console.error("Delete expense error:", error);
        showStatus(expenseListStatus, `Could not delete expense: ${error.message}`, "error");
        button.disabled = false;
    }
}

// Load totals grouped by category.
async function loadCategoryTotals() {
    try {
        const response = await fetch(`${API_URL}/expenses/categories`);

        if (!response.ok) {
            throw new Error(`Request failed: ${response.status}`);
        }

        const categories = await response.json();
        categoryTotals.replaceChildren();

        if (categories.length === 0) {
            const message = document.createElement("p");
            message.textContent = "No category totals yet.";
            categoryTotals.appendChild(message);
            return;
        }

        for (const item of categories) {
            const card = document.createElement("article");
            card.className = "category-card";

            const name = document.createElement("p");
            name.textContent = item.category;

            const total = document.createElement("h3");
            total.textContent = formatMoney(item.total_spent);

            const count = document.createElement("p");
            count.textContent = `${item.expense_count} expense(s)`;

            card.append(name, total, count);
            categoryTotals.appendChild(card);
        }
    } catch (error) {
        console.error("Category totals error:", error);
        categoryTotals.textContent = "Could not load category totals.";
    }
}

// Submit the Add Expense form to FastAPI.
expenseForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const title = document.getElementById("description").value.trim();
    const amount = Number(document.getElementById("amount").value);
    const category = document.getElementById("category").value.trim();
    const expenseDate = document.getElementById("expense-date").value;

    if (!title || !category || !expenseDate || !Number.isFinite(amount) || amount <= 0) {
        showStatus(formStatus, "Enter a description, valid amount, category, and date.", "error");
        return;
    }

    const expense = {
        title: title,
        amount: amount,
        category: category,
        expense_date: expenseDate,
        notes: ""
    };

    const submitButton = expenseForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    showStatus(formStatus, "Saving expense...");

    try {
        const response = await fetch(`${API_URL}/expenses`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(expense)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            const detail = Array.isArray(errorData.detail)
                ? errorData.detail.map(item => item.msg).join(", ")
                : errorData.detail;

            throw new Error(detail || `Request failed: ${response.status}`);
        }

        showStatus(formStatus, "Expense added successfully!", "success");
        expenseForm.reset();

        // Default the date back to today after resetting the form.
        document.getElementById("expense-date").value =
            new Date().toLocaleDateString("en-CA");

        await Promise.all([
            loadMonthlySummary(),
            loadExpenses(),
            loadCategoryTotals()
        ]);
    } catch (error) {
        console.error("Add expense error:", error);
        showStatus(formStatus, `Could not save expense: ${error.message}`, "error");
    } finally {
        submitButton.disabled = false;
    }
});

function updateIncomeDateField() {
    const isOneTime = incomeFrequency.value === "once";
    incomeDateField.hidden = !isOneTime;
    incomeDate.required = isOneTime;
}

incomeFrequency.addEventListener("change", updateIncomeDateField);
updateIncomeDateField();

incomeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const frequency = incomeFrequency.value;
    const income = {
        person: document.getElementById("income-person").value.trim(),
        source: document.getElementById("income-source").value.trim(),
        amount: Number(document.getElementById("income-amount").value),
        frequency: frequency,
        income_date: frequency === "once" ? incomeDate.value : null
    };
    const submitButton = incomeForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    showStatus(recurringStatus, "Saving income...");

    try {
        const response = await fetch(`${API_URL}/recurring/income`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(income)
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            const detail = Array.isArray(error.detail)
                ? error.detail.map(item => item.msg).join(", ")
                : error.detail;
            throw new Error(detail || `Request failed: ${response.status}`);
        }

        incomeForm.reset();
        updateIncomeDateField();
        if (frequency === "once") {
            const [year, month] = income.income_date.split("-").map(Number);
            summaryYear.value = String(year);
            summaryMonth.value = String(month);
        }

        const refreshed = await Promise.all([
            loadRecurringPlan(),
            loadMonthlySummary()
        ]);
        showStatus(
            recurringStatus,
            refreshed[0]
                ? "Income added successfully."
                : "Income was added, but the list could not be refreshed.",
            refreshed[0] ? "success" : "error"
        );
    } catch (error) {
        console.error("Add income error:", error);
        showStatus(recurringStatus, `Could not add income: ${error.message}`, "error");
    } finally {
        submitButton.disabled = false;
    }
});

billForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const bill = {
        title: document.getElementById("bill-title").value.trim(),
        amount: Number(document.getElementById("bill-amount").value),
        category: document.getElementById("bill-category").value.trim(),
        due_day: Number(document.getElementById("bill-due-day").value)
    };
    const submitButton = billForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    showStatus(recurringStatus, "Saving monthly bill...");

    try {
        const response = await fetch(`${API_URL}/recurring/bills`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(bill)
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            const detail = Array.isArray(error.detail)
                ? error.detail.map(item => item.msg).join(", ")
                : error.detail;
            throw new Error(detail || `Request failed: ${response.status}`);
        }

        billForm.reset();
        document.getElementById("bill-category").value = "Bills";
        document.getElementById("bill-due-day").value = "1";
        const refreshed = await loadRecurringPlan();
        showStatus(
            recurringStatus,
            refreshed
                ? "Monthly bill added successfully."
                : "Monthly bill was added, but the list could not be refreshed.",
            refreshed ? "success" : "error"
        );
    } catch (error) {
        console.error("Add monthly bill error:", error);
        showStatus(recurringStatus, `Could not add bill: ${error.message}`, "error");
    } finally {
        submitButton.disabled = false;
    }
});

// Reload the summary when the month or year changes.
document.getElementById("load-summary").addEventListener("click", async () => {
    await Promise.all([loadMonthlySummary(), loadRecurringPlan()]);
});

// Set default values and load the existing data when the page opens.
document.getElementById("expense-date").value =
    new Date().toLocaleDateString("en-CA");

loadMonthlySummary();
loadExpenses();
loadCategoryTotals();
loadRecurringPlan();
