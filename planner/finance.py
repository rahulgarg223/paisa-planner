"""Pure finance calculations for Paisa Planner.

Nothing in this module imports Streamlit, so every function can be unit-tested
on its own. Amounts are monthly rupee figures unless a name says otherwise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping

CATEGORIES = [
    "Rent / Housing",
    "Food & Groceries",
    "Transport",
    "Bills & Utilities",
    "EMI / Loans",
    "Insurance",
    "Health",
    "Education",
    "Family support",
    "Shopping",
    "Eating out",
    "Entertainment",
    "Subscriptions",
    "Other",
]
KINDS = ("Need", "Want")
RISK_LEVELS = ("Conservative", "Moderate", "Aggressive")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def to_amount(value) -> float:
    """Coerce a table cell to a non-negative float (blank / NaN / text -> 0)."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return 0.0
    return x if math.isfinite(x) and x > 0 else 0.0


def inr(n: float) -> str:
    """Format a number with Indian digit grouping: 1234567 -> ₹12,34,567."""
    neg = n < 0
    digits = str(int(round(abs(n))))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups) + "," + tail
    return ("−₹" if neg else "₹") + digits


def short_inr(n: float) -> str:
    """Compact lakh / crore format: 2500000 -> ₹25.00 L, 31000000 -> ₹3.10 Cr."""
    a, sign = abs(n), ("−₹" if n < 0 else "₹")
    if a >= 1e7:
        return f"{sign}{a / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"{sign}{a / 1e5:.2f} L"
    return inr(n)


# --------------------------------------------------------------------------- #
# Budget
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BudgetSummary:
    income: float
    expenses: float
    needs: float
    wants: float

    @property
    def surplus(self) -> float:
        return self.income - self.expenses

    @property
    def savings_rate(self) -> float:
        return self.surplus / self.income if self.income > 0 else 0.0


def summarize(income_rows: Iterable[Mapping], expense_rows: Iterable[Mapping]) -> BudgetSummary:
    """Total up income rows ({amount}) and expense rows ({amount, type})."""
    income = sum(to_amount(r.get("amount")) for r in income_rows)
    expense_rows = list(expense_rows)
    expenses = sum(to_amount(r.get("amount")) for r in expense_rows)
    needs = sum(to_amount(r.get("amount")) for r in expense_rows if r.get("type") != "Want")
    return BudgetSummary(income=income, expenses=expenses, needs=needs, wants=expenses - needs)


def category_totals(expense_rows: Iterable[Mapping]) -> dict[str, float]:
    """Spending per category, largest first. Blank categories count as Other."""
    totals: dict[str, float] = {}
    for r in expense_rows:
        amt = to_amount(r.get("amount"))
        if amt:
            cat = r.get("category") or "Other"
            totals[cat] = totals.get(cat, 0.0) + amt
    return dict(sorted(totals.items(), key=lambda kv: kv[1], reverse=True))


def rule_50_30_20(s: BudgetSummary) -> list[dict]:
    """Compare needs / wants / savings shares of income with the 50/30/20 rule."""
    inc = s.income or 1.0
    rows = [
        ("Needs", s.needs / inc, 0.50, "max"),
        ("Wants", s.wants / inc, 0.30, "max"),
        ("Savings", max(s.surplus, 0) / inc, 0.20, "min"),
    ]
    out = []
    for name, actual, target, kind in rows:
        if kind == "max":
            ok, close = actual <= target, actual <= target + 0.08
        else:
            ok, close = actual >= target, actual >= target - 0.05
        status = "On track" if ok else "Close" if close else "Off track"
        out.append({"name": name, "actual": actual, "target": target, "kind": kind, "status": status})
    return out


# --------------------------------------------------------------------------- #
# SIP
# --------------------------------------------------------------------------- #
def sip_series(monthly: float, annual_return_pct: float, years: int, step_up_pct: float = 0.0) -> list[dict]:
    """Year-by-year SIP growth.

    Money goes in at the start of each month and compounds monthly. The monthly
    amount rises by ``step_up_pct`` at the start of every new year.
    Returns [{year, invested, value}], starting with year 0.
    """
    r = annual_return_pct / 100 / 12
    balance = invested = 0.0
    amount = float(monthly)
    out = [{"year": 0, "invested": 0.0, "value": 0.0}]
    for year in range(1, int(years) + 1):
        for _ in range(12):
            balance = (balance + amount) * (1 + r)
            invested += amount
        out.append({"year": year, "invested": invested, "value": balance})
        amount *= 1 + step_up_pct / 100
    return out


def inflate(amount: float, years: float, inflation_pct: float) -> float:
    """What today's ``amount`` will cost after ``years`` of inflation."""
    return amount * (1 + inflation_pct / 100) ** years


def required_sip(target: float, years: float, annual_return_pct: float) -> float:
    """Flat monthly SIP (start-of-month) that grows to ``target`` in ``years``."""
    n = round(years * 12)
    if n <= 0:
        raise ValueError("years must be positive")
    r = annual_return_pct / 100 / 12
    if r == 0:
        return target / n
    return target / ((((1 + r) ** n - 1) / r) * (1 + r))


# --------------------------------------------------------------------------- #
# Allocation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Asset:
    key: str
    name: str
    pct: float
    note: str


_EQUITY_SPLIT = {  # large-cap / flexi-cap / mid+small-cap share of equity
    "conservative": (0.7, 0.3, 0.0),
    "moderate": (0.5, 0.3, 0.2),
    "aggressive": (0.4, 0.3, 0.3),
}


def equity_share(age: int, horizon_years: int, risk: str) -> int:
    """Rule of thumb: start near (100 - age), shift for risk, cap by horizon."""
    risk = risk.lower()
    eq = 100 - age + {"aggressive": 10, "conservative": -15}.get(risk, 0)
    if horizon_years < 3:
        eq = min(eq, 20)
    elif horizon_years < 5:
        eq = min(eq, 50)
    elif horizon_years < 8:
        eq = min(eq, 70)
    eq = max(10, min(85, eq))
    return int(eq / 5 + 0.5) * 5


def suggest_allocation(age: int, horizon_years: int, risk: str, gold_pct: int = 10) -> list[Asset]:
    eq = equity_share(age, horizon_years, risk)
    debt = 100 - eq - gold_pct
    large, flexi, small = _EQUITY_SPLIT.get(risk.lower(), _EQUITY_SPLIT["moderate"])
    assets = [
        Asset("large", "Large-cap / Nifty 50 index fund", eq * large,
              "Low-cost core holding in India's 50 biggest companies."),
        Asset("flexi", "Flexi-cap fund", eq * flexi,
              "Fund manager moves across large, mid and small caps."),
        Asset("midsmall", "Mid & small-cap funds", eq * small,
              "Higher growth with sharper falls. Needs 7+ years."),
        Asset("debt", "Debt: PPF / short-duration debt fund", debt,
              "Stability. PPF is tax-free with a 15-year lock-in."),
        Asset("gold", "Gold ETF / gold fund", gold_pct,
              "Hedge for when equity markets fall."),
    ]
    return [a for a in assets if a.pct > 0.4]


def emergency_plan(monthly_expenses: float, saved: float, surplus: float, months: int = 6) -> dict:
    """Split the surplus between topping up the emergency fund and investing.

    While the fund is short of ``months`` x expenses, up to half the surplus
    goes to it; the rest is invested.
    """
    target = months * monthly_expenses
    gap = max(0.0, target - saved)
    usable = max(surplus, 0.0)
    to_emergency = min(usable * 0.5, gap) if gap > 0 else 0.0
    return {
        "target": target,
        "gap": gap,
        "months_covered": saved / monthly_expenses if monthly_expenses > 0 else 0.0,
        "to_emergency": to_emergency,
        "to_invest": usable - to_emergency,
        "months_to_fill": math.ceil(gap / to_emergency) if to_emergency > 0 else None,
    }


# --------------------------------------------------------------------------- #
# Snapshot for the AI assistant
# --------------------------------------------------------------------------- #
def snapshot_text(income_rows, expense_rows, profile: Mapping, sip: Mapping) -> str:
    """Plain-text summary of everything on screen, sent to the LLM each turn."""
    income_rows, expense_rows = list(income_rows), list(expense_rows)
    s = summarize(income_rows, expense_rows)
    alloc = suggest_allocation(profile["age"], profile["horizon"], profile["risk"])
    series = sip_series(sip["amount"], sip["return"], sip["years"], sip["step_up"])[-1]
    em = emergency_plan(s.expenses, profile["emergency"], s.surplus)

    lines = ["MONTHLY INCOME (INR)"]
    lines += [f"- {r.get('name') or 'Unnamed'}: {inr(to_amount(r.get('amount')))}" for r in income_rows]
    lines += [f"Total: {inr(s.income)}", "", "MONTHLY EXPENSES (INR)"]
    lines += [
        f"- {r.get('name') or 'Unnamed'} [{r.get('category') or 'Other'}, {r.get('type') or 'Need'}]: "
        f"{inr(to_amount(r.get('amount')))}"
        for r in expense_rows
    ]
    lines += [
        f"Total: {inr(s.expenses)} (needs {inr(s.needs)}, wants {inr(s.wants)})",
        "",
        f"Surplus: {inr(s.surplus)} / month, savings rate {s.savings_rate * 100:.1f}%",
        f"Emergency fund saved: {inr(profile['emergency'])} "
        f"({em['months_covered']:.1f} months of expenses; target 6 months = {inr(em['target'])})",
        "",
        f"PROFILE: age {profile['age']}, horizon {profile['horizon']} years, risk {profile['risk']}",
        "SUGGESTED ALLOCATION: " + "; ".join(f"{a.name} {a.pct:.0f}%" for a in alloc),
        "",
        f"SIP PLAN: {inr(sip['amount'])}/month at {sip['return']}% for {sip['years']} years, "
        f"{sip['step_up']}% annual step-up -> invested {short_inr(series['invested'])}, "
        f"value {short_inr(series['value'])}",
    ]
    return "\n".join(lines)
