import pytest

from planner import finance as fin

INCOME = [{"name": "Salary", "amount": 50000}, {"name": "Side", "amount": 10000}]
EXPENSES = [
    {"name": "Rent", "category": "Rent / Housing", "type": "Need", "amount": 20000},
    {"name": "Food", "category": "Food & Groceries", "type": "Need", "amount": 8000},
    {"name": "Movies", "category": "Entertainment", "type": "Want", "amount": 2000},
    {"name": "Blank", "category": None, "type": "Want", "amount": None},
]


def test_inr_uses_indian_grouping():
    assert fin.inr(1234567) == "₹12,34,567"
    assert fin.inr(999) == "₹999"
    assert fin.inr(-15000) == "−₹15,000"


def test_short_inr_lakh_and_crore():
    assert fin.short_inr(2_500_000) == "₹25.00 L"
    assert fin.short_inr(31_000_000) == "₹3.10 Cr"
    assert fin.short_inr(4500) == "₹4,500"


def test_summarize_handles_blank_cells():
    s = fin.summarize(INCOME, EXPENSES)
    assert s.income == 60000
    assert s.expenses == 30000
    assert s.needs == 28000 and s.wants == 2000
    assert s.surplus == 30000
    assert s.savings_rate == pytest.approx(0.5)


def test_category_totals_sorted_desc():
    cats = fin.category_totals(EXPENSES)
    assert list(cats) == ["Rent / Housing", "Food & Groceries", "Entertainment"]


def test_rule_50_30_20_status():
    rows = {r["name"]: r for r in fin.rule_50_30_20(fin.summarize(INCOME, EXPENSES))}
    assert rows["Needs"]["status"] == "On track"  # 46.7% <= 50%
    assert rows["Savings"]["status"] == "On track"  # 50% >= 20%


def test_sip_zero_return_equals_invested():
    end = fin.sip_series(10000, 0, 10)[-1]
    assert end["invested"] == end["value"] == 1_200_000


def test_sip_step_up_increases_contributions():
    flat = fin.sip_series(10000, 12, 5)[-1]
    stepped = fin.sip_series(10000, 12, 5, step_up_pct=10)[-1]
    assert stepped["invested"] > flat["invested"]
    assert stepped["value"] > flat["value"]


def test_sip_matches_standard_formula():
    # 10k/month, 12% p.a., 10 years, start-of-month: ~₹23.23 lakh
    assert fin.sip_series(10000, 12, 10)[-1]["value"] == pytest.approx(2_323_391, rel=1e-4)


def test_required_sip_round_trips():
    need = fin.required_sip(5_000_000, 15, 12)
    assert fin.sip_series(need, 12, 15)[-1]["value"] == pytest.approx(5_000_000, rel=1e-9)
    assert fin.required_sip(120_000, 1, 0) == pytest.approx(10_000)


def test_inflate():
    assert fin.inflate(100, 10, 6) == pytest.approx(100 * 1.06 ** 10)


@pytest.mark.parametrize("age,horizon,risk", [(22, 15, "Aggressive"), (45, 10, "Moderate"), (30, 2, "Conservative")])
def test_allocation_sums_to_100(age, horizon, risk):
    assert sum(a.pct for a in fin.suggest_allocation(age, horizon, risk)) == pytest.approx(100)


def test_short_horizon_caps_equity():
    assert fin.equity_share(22, 2, "Aggressive") == 20
    assert fin.equity_share(22, 4, "Aggressive") == 50


def test_conservative_has_no_small_caps():
    keys = {a.key for a in fin.suggest_allocation(25, 15, "Conservative")}
    assert "midsmall" not in keys


def test_emergency_plan_splits_surplus():
    em = fin.emergency_plan(monthly_expenses=30000, saved=60000, surplus=20000)
    assert em["target"] == 180000 and em["gap"] == 120000
    assert em["to_emergency"] == 10000 and em["to_invest"] == 10000
    assert em["months_to_fill"] == 12


def test_emergency_plan_full_fund():
    em = fin.emergency_plan(30000, 200000, 20000)
    assert em["gap"] == 0 and em["to_invest"] == 20000 and em["months_to_fill"] is None


def test_snapshot_mentions_key_numbers():
    text = fin.snapshot_text(
        INCOME, EXPENSES,
        profile={"age": 25, "horizon": 10, "risk": "Moderate", "emergency": 50000},
        sip={"amount": 15000, "return": 12, "years": 10, "step_up": 10},
    )
    assert "₹60,000" in text and "₹30,000" in text and "SIP PLAN" in text
    assert "nan" not in text.lower()
