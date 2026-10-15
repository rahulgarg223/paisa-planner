"""Paisa Planner — monthly budget, SIP and allocation planner with an AI assistant.

Run locally:  streamlit run app.py
"""
from __future__ import annotations

import json
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from planner import finance as fin
from planner.ai import DEFAULT_MODEL, AssistantError, stream_reply

st.set_page_config(page_title="Paisa Planner", page_icon="💰", layout="wide")

ACCENT, SAFFRON, GOOD, BAD, MUTED = "#0E6A5E", "#B8700C", "#1D7A43", "#B13A2F", "#8A9A95"
ASSET_COLORS = {"large": "#0E6A5E", "flexi": "#2E8F7E", "midsmall": "#5BAE9B", "debt": "#5A6E9A", "gold": "#B8700C"}
STATUS_ICON = {"On track": "🟢", "Close": "🟡", "Off track": "🔴"}

EXAMPLE_INCOME = [
    {"name": "Salary (in-hand)", "amount": 65000},
    {"name": "Freelance", "amount": 8000},
]
EXAMPLE_EXPENSES = [
    {"name": "Flat rent", "category": "Rent / Housing", "type": "Need", "amount": 15000},
    {"name": "Groceries", "category": "Food & Groceries", "type": "Need", "amount": 6000},
    {"name": "Electricity + WiFi", "category": "Bills & Utilities", "type": "Need", "amount": 2500},
    {"name": "Metro + cabs", "category": "Transport", "type": "Need", "amount": 3000},
    {"name": "Mobile plan", "category": "Bills & Utilities", "type": "Need", "amount": 500},
    {"name": "Health insurance", "category": "Insurance", "type": "Need", "amount": 1200},
    {"name": "Sent home", "category": "Family support", "type": "Need", "amount": 5000},
    {"name": "Swiggy / Zomato", "category": "Eating out", "type": "Want", "amount": 4000},
    {"name": "OTT apps", "category": "Subscriptions", "type": "Want", "amount": 700},
    {"name": "Clothes & gadgets", "category": "Shopping", "type": "Want", "amount": 3500},
]
DEFAULTS = {
    "sip_amt": 15000, "sip_ret": 12.0, "sip_yrs": 15, "sip_step": 10.0,
    "goal_amt": 2500000, "goal_yrs": 10, "goal_ret": 12.0, "goal_inf": 6.0,
    "age": 24, "horizon": 12, "risk": "Moderate", "emergency": 60000,
}
SETTING_KEYS = list(DEFAULTS)
QUICK_PROMPTS = {
    "Analyse my budget": "Analyse my monthly budget. What looks healthy, what needs attention, and give 3 specific changes with rupee amounts.",
    "Where can I cut?": "Which of my expenses can I cut, and by how much, to invest more? Be specific to my numbers.",
    "Build my SIP plan": "Build a monthly SIP plan from my surplus: how much into which fund categories, and what it could grow to in 10 and 20 years.",
    "Explain my allocation": "Explain my suggested allocation in simple terms and what kind of funds fit each part.",
}


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
def init_state() -> None:
    ss = st.session_state
    if "income_df" not in ss:
        ss.income_df = pd.DataFrame(EXAMPLE_INCOME)
        ss.expense_df = pd.DataFrame(EXAMPLE_EXPENSES)
        ss.editor_ver = 0
        ss.chat = []
        ss.loaded_file = None
    for k, v in DEFAULTS.items():
        ss.setdefault(k, v)


def start_blank() -> None:
    ss = st.session_state
    ss.income_df = pd.DataFrame([{"name": "Salary", "amount": 0}])
    ss.expense_df = pd.DataFrame(columns=["name", "category", "type", "amount"])
    ss.emergency = 0
    ss.editor_ver += 1


def load_plan(data: dict) -> None:
    ss = st.session_state
    ss.income_df = pd.DataFrame(data.get("income", []), columns=["name", "amount"])
    ss.expense_df = pd.DataFrame(data.get("expenses", []), columns=["name", "category", "type", "amount"])
    for k in SETTING_KEYS:
        if k in data.get("settings", {}):
            ss[k] = data["settings"][k]
    ss.editor_ver += 1


def use_surplus(surplus: float) -> None:
    st.session_state.sip_amt = max(0, int(surplus // 500 * 500))


def get_secret(name: str) -> str | None:
    try:
        value = st.secrets.get(name)
    except Exception:  # no secrets.toml present
        value = None
    return value or os.environ.get(name)


def records(df: pd.DataFrame) -> list[dict]:
    return df.where(pd.notna(df), None).to_dict("records")


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def lakh_ticks(max_value: float, n: int = 5) -> tuple[list[float], list[str]]:
    if max_value <= 0:
        return [0], ["₹0"]
    raw = max_value / (n - 1)
    mag = 10 ** len(str(int(raw))) / 10
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    vals = [i * step for i in range(n) if i * step <= max_value * 1.05 + step]
    return vals, [fin.short_inr(v) for v in vals]


def rule_chart(rows: list[dict]) -> go.Figure:
    names = [r["name"] for r in rows]
    colors = [ACCENT, SAFFRON, GOOD]
    fig = go.Figure()
    fig.add_bar(y=names, x=[r["actual"] * 100 for r in rows], orientation="h", marker_color=colors,
                text=[f"{r['actual'] * 100:.0f}%" for r in rows], textposition="outside",
                hovertemplate="%{y}: %{x:.1f}% of income<extra></extra>", name="Actual")
    fig.add_scatter(y=names, x=[r["target"] * 100 for r in rows], mode="markers",
                    marker=dict(symbol="line-ns", size=26, line=dict(width=3, color="#555")),
                    hovertemplate="Target %{x:.0f}%<extra></extra>", name="Target")
    fig.update_layout(height=220, margin=dict(l=0, r=30, t=10, b=10), showlegend=False,
                      xaxis=dict(ticksuffix="%", range=[0, max(70, max(r["actual"] for r in rows) * 110)]),
                      yaxis=dict(autorange="reversed"))
    return fig


def category_chart(totals: dict[str, float]) -> go.Figure:
    cats, vals = list(totals), list(totals.values())
    fig = go.Figure(go.Bar(y=cats, x=vals, orientation="h", marker_color=ACCENT,
                           text=[fin.inr(v) for v in vals], textposition="outside",
                           hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
    fig.update_layout(height=max(180, 34 * len(cats) + 40), margin=dict(l=0, r=60, t=10, b=10),
                      yaxis=dict(autorange="reversed"), xaxis=dict(showticklabels=False, showgrid=False))
    return fig


def sip_chart(series: list[dict]) -> go.Figure:
    years = [p["year"] for p in series]
    values, invested = [p["value"] for p in series], [p["invested"] for p in series]
    fig = go.Figure()
    fig.add_scatter(x=years, y=values, name="Portfolio value", mode="lines", fill="tozeroy",
                    line=dict(color=ACCENT, width=3), fillcolor="rgba(14,106,94,0.15)",
                    customdata=[fin.short_inr(v) for v in values],
                    hovertemplate="Year %{x}: %{customdata}<extra>Value</extra>")
    fig.add_scatter(x=years, y=invested, name="Amount invested", mode="lines",
                    line=dict(color=MUTED, width=2, dash="dash"),
                    customdata=[fin.short_inr(v) for v in invested],
                    hovertemplate="Year %{x}: %{customdata}<extra>Invested</extra>")
    tickvals, ticktext = lakh_ticks(max(values))
    fig.update_layout(height=330, margin=dict(l=0, r=10, t=10, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=1.08, x=0),
                      xaxis=dict(title="Year", dtick=max(1, len(years) // 8)),
                      yaxis=dict(tickvals=tickvals, ticktext=ticktext))
    return fig


def allocation_chart(assets: list[fin.Asset]) -> go.Figure:
    fig = go.Figure()
    for a in assets:
        fig.add_bar(y=["Mix"], x=[a.pct], orientation="h", name=a.name, marker_color=ASSET_COLORS[a.key],
                    text=f"{a.pct:.0f}%" if a.pct >= 8 else "", textposition="inside",
                    hovertemplate=f"{a.name}: {a.pct:.0f}%<extra></extra>")
    fig.update_layout(barmode="stack", height=150, margin=dict(l=0, r=0, t=0, b=0),
                      xaxis=dict(visible=False, range=[0, 100]), yaxis=dict(visible=False),
                      legend=dict(orientation="h", y=-0.15, x=0))
    return fig


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
init_state()
ss = st.session_state

st.title("💰 Paisa Planner")
st.caption("Plan the month, then put the surplus to work.")
top = st.container()
tab_budget, tab_sip, tab_alloc, tab_ai = st.tabs(["Budget", "SIP planner", "Allocation", "AI assistant"])

# ---- Budget -------------------------------------------------------------- #
with tab_budget:
    left, right = st.columns([1.25, 1], gap="large")
    with left:
        st.subheader("Income")
        income_df = st.data_editor(
            ss.income_df, key=f"income_{ss.editor_ver}", num_rows="dynamic", hide_index=True,
            column_config={
                "name": st.column_config.TextColumn("Source", required=True),
                "amount": st.column_config.NumberColumn("₹ / month", min_value=0, step=500, format="₹%d"),
            },
        )
        st.subheader("Expenses")
        st.caption("Mark each line a **Need** (rent, groceries, EMIs, insurance) or a **Want** (eating out, shopping, OTT).")
        expense_df = st.data_editor(
            ss.expense_df, key=f"expenses_{ss.editor_ver}", num_rows="dynamic", hide_index=True,
            column_config={
                "name": st.column_config.TextColumn("Item", required=True),
                "category": st.column_config.SelectboxColumn("Category", options=fin.CATEGORIES, default="Other"),
                "type": st.column_config.SelectboxColumn("Type", options=list(fin.KINDS), default="Need"),
                "amount": st.column_config.NumberColumn("₹ / month", min_value=0, step=100, format="₹%d"),
            },
        )

    income_rows, expense_rows = records(income_df), records(expense_df)
    summary = fin.summarize(income_rows, expense_rows)

    with right:
        st.subheader("50 / 30 / 20 check")
        rule_rows = fin.rule_50_30_20(summary)
        st.plotly_chart(rule_chart(rule_rows), config={"displayModeBar": False})
        for r in rule_rows:
            sign = "≤" if r["kind"] == "max" else "≥"
            st.markdown(f"{STATUS_ICON[r['status']]} **{r['name']}** {r['actual'] * 100:.0f}% "
                        f"(target {sign}{r['target'] * 100:.0f}%) · {r['status']}")
        st.caption("The grey tick is the target share of income. Savings is whatever is left after all expenses.")

        st.subheader("Where the money goes")
        cats = fin.category_totals(expense_rows)
        if cats:
            st.plotly_chart(category_chart(cats), config={"displayModeBar": False})
        else:
            st.info("Add expenses to see the breakdown.")

    with st.expander("Save or load your plan"):
        plan = {
            "income": income_rows,
            "expenses": expense_rows,
            "settings": {k: ss[k] for k in SETTING_KEYS},
        }
        c1, c2 = st.columns(2)
        c1.download_button("Download plan (.json)", json.dumps(plan, indent=2, default=str),
                           file_name="paisa-plan.json", mime="application/json")
        upload = c2.file_uploader("Load a saved plan", type="json", label_visibility="collapsed")
        if upload is not None and upload.file_id != ss.loaded_file:
            ss.loaded_file = upload.file_id
            try:
                load_plan(json.load(upload))
                st.rerun()
            except (ValueError, KeyError, TypeError):
                st.error("That file isn't a Paisa Planner plan. Download one from here to see the format.")
        st.caption("Plans live only in this browser session. Download one to keep it.")

# ---- Summary strip (rendered at the top, filled after the tables) -------- #
with top:
    is_example = income_rows == EXAMPLE_INCOME and expense_rows == EXAMPLE_EXPENSES
    if is_example:
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.info("Showing example figures. Edit the tables below or start from a blank plan.")
        c2.button("Start blank", on_click=start_blank)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Income / month", fin.inr(summary.income))
    m2.metric("Expenses / month", fin.inr(summary.expenses))
    m3.metric("Surplus to invest", fin.inr(summary.surplus))
    m4.metric("Savings rate", f"{summary.savings_rate * 100:.0f}%")

# ---- SIP ----------------------------------------------------------------- #
with tab_sip:
    left, right = st.columns([1.25, 1], gap="large")
    with left:
        st.subheader("SIP growth")
        c1, c2, c3, c4 = st.columns(4)
        c1.number_input("Monthly SIP (₹)", key="sip_amt", min_value=0, step=500)
        c2.number_input("Return (% p.a.)", key="sip_ret", min_value=0.0, max_value=30.0, step=0.5)
        c3.number_input("Years", key="sip_yrs", min_value=1, max_value=40, step=1)
        c4.number_input("Step-up (% / yr)", key="sip_step", min_value=0.0, max_value=50.0, step=1.0)
        st.button(f"Use my surplus ({fin.inr(max(summary.surplus, 0))})", on_click=use_surplus, args=(summary.surplus,))

        series = fin.sip_series(ss.sip_amt, ss.sip_ret, ss.sip_yrs, ss.sip_step)
        end = series[-1]
        f1, f2, f3 = st.columns(3)
        f1.metric("You invest", fin.short_inr(end["invested"]))
        f2.metric("Est. gains", fin.short_inr(end["value"] - end["invested"]))
        f3.metric("Maturity value", fin.short_inr(end["value"]))
        st.plotly_chart(sip_chart(series), config={"displayModeBar": False})
        st.caption("Assumes a fixed return, compounded monthly, invested at the start of each month. "
                   "10–12% is a common long-run assumption for Indian equity funds, not a promise.")

    with right:
        st.subheader("SIP needed for a goal")
        c1, c2 = st.columns(2)
        c1.number_input("Goal amount, today's ₹", key="goal_amt", min_value=0, step=50000)
        c2.number_input("In years", key="goal_yrs", min_value=1, max_value=40)
        c1.number_input("Expected return (%)", key="goal_ret", min_value=0.0, max_value=30.0, step=0.5)
        c2.number_input("Inflation (%)", key="goal_inf", min_value=0.0, max_value=15.0, step=0.5)
        future = fin.inflate(ss.goal_amt, ss.goal_yrs, ss.goal_inf)
        need = fin.required_sip(future, ss.goal_yrs, ss.goal_ret)
        st.metric("Monthly SIP needed", fin.inr(need))
        st.write(f"Today's {fin.short_inr(ss.goal_amt)} will cost about **{fin.short_inr(future)}** "
                 f"in {ss.goal_yrs} years at {ss.goal_inf}% inflation.")
        if summary.surplus > 0:
            if need <= summary.surplus:
                st.success(f"Fits: that's {need / summary.surplus * 100:.0f}% of your monthly surplus.")
            else:
                st.warning(f"Your surplus is {fin.inr(summary.surplus)}, so stretch the timeline or trim expenses.")

        st.subheader("Tax notes")
        st.markdown(
            "- Equity funds held over 12 months: long-term gains above ₹1.25 lakh a year taxed at 12.5%.\n"
            "- Equity funds sold within 12 months: short-term gains taxed at 20%.\n"
            "- ELSS gives an 80C deduction (old tax regime only) with a 3-year lock-in."
        )
        st.caption("Rates as of FY 2025-26. Check the current budget before filing.")

# ---- Allocation ---------------------------------------------------------- #
with tab_alloc:
    left, right = st.columns([1.25, 1], gap="large")
    with left:
        st.subheader("Your profile")
        c1, c2, c3 = st.columns(3)
        c1.number_input("Age", key="age", min_value=16, max_value=80)
        c2.number_input("Horizon (years)", key="horizon", min_value=1, max_value=40)
        c3.number_input("Emergency fund saved (₹)", key="emergency", min_value=0, step=5000)
        st.radio("Risk appetite", fin.RISK_LEVELS, key="risk", horizontal=True)

        assets = fin.suggest_allocation(ss.age, ss.horizon, ss.risk)
        em = fin.emergency_plan(summary.expenses, ss.emergency, summary.surplus)
        st.subheader(f"Suggested mix · investing {fin.inr(em['to_invest'])}/month")
        st.plotly_chart(allocation_chart(assets), config={"displayModeBar": False})
        st.dataframe(
            pd.DataFrame([{"Asset": a.name, "Share": f"{a.pct:.0f}%",
                           "₹ / month": fin.inr(em["to_invest"] * a.pct / 100), "Why": a.note} for a in assets]),
            hide_index=True,
        )
        st.caption("Rule of thumb: equity starts near 100 minus your age, then shifts with risk appetite "
                   "and horizon. Gold stays near 10% as a hedge.")

    with right:
        st.subheader("Emergency fund")
        st.progress(min(1.0, ss.emergency / em["target"]) if em["target"] else 0.0,
                    text=f"{em['months_covered']:.1f} of 6 months covered · target {fin.inr(em['target'])}")
        if em["gap"] > 0:
            msg = (f"You're {fin.inr(em['gap'])} short. Until it's full, send **{fin.inr(em['to_emergency'])}**/month "
                   f"to a liquid fund or sweep FD and invest the rest.")
            if em["months_to_fill"]:
                msg += f" At that pace it fills in about {em['months_to_fill']} months."
            st.warning(msg)
        else:
            st.success("Your emergency fund is full, so the whole surplus can go into the mix.")

        st.subheader("Order of priorities")
        st.markdown(
            "1. Health and term insurance in place before investing.\n"
            "2. Clear high-interest debt (credit cards, personal loans).\n"
            "3. Build 6 months of expenses as an emergency fund.\n"
            "4. Start SIPs in the suggested mix and raise them every year."
        )
        st.subheader("Direct stocks")
        st.write("If you pick stocks yourself, cap them at 10–20% of your equity share while you learn. "
                 "Index funds already hold the Nifty 50, so direct picks should add something you've researched.")

# ---- AI assistant -------------------------------------------------------- #
with tab_ai:
    snapshot = fin.snapshot_text(
        income_rows, expense_rows,
        profile={"age": ss.age, "horizon": ss.horizon, "risk": ss.risk, "emergency": ss.emergency},
        sip={"amount": ss.sip_amt, "return": ss.sip_ret, "years": ss.sip_yrs, "step_up": ss.sip_step},
    )
    api_key = get_secret("GEMINI_API_KEY") or ss.get("user_api_key")
    model = get_secret("GEMINI_MODEL") or DEFAULT_MODEL

    left, right = st.columns([1.6, 1], gap="large")
    with right:
        with st.expander("What the assistant sees", expanded=False):
            st.code(snapshot, language=None)
        if not get_secret("GEMINI_API_KEY"):
            st.text_input("Gemini API key", key="user_api_key", type="password",
                          help="Get a free key at aistudio.google.com/apikey. It's kept only for this session.")
        st.caption(f"Model: `{model}`. General education, not advice from a SEBI-registered adviser.")

    with left:
        head, clear = st.columns([4, 1], vertical_alignment="center")
        head.subheader("Ask about your money")
        if clear.button("Clear chat", disabled=not ss.chat):
            ss.chat = []
            st.rerun()

        cols = st.columns(len(QUICK_PROMPTS))
        for col, (label, prompt) in zip(cols, QUICK_PROMPTS.items()):
            if col.button(label, width="stretch", disabled=not api_key):
                ss.pending = prompt

        if not api_key:
            st.info("Add a Gemini API key to switch on the assistant: set GEMINI_API_KEY in "
                    "`.streamlit/secrets.toml`, or paste one in the box on the right.")

        chat_box = st.container(height=480)
        with chat_box:
            for m in ss.chat:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

        typed = st.chat_input("e.g. Should I prepay my bike loan or start a SIP?", disabled=not api_key)
        question = typed or ss.pop("pending", None)
        if question and api_key:
            ss.chat.append({"role": "user", "content": question})
            with chat_box:
                with st.chat_message("user"):
                    st.markdown(question)
                with st.chat_message("assistant"):
                    try:
                        reply = st.write_stream(stream_reply(api_key, snapshot, ss.chat, model=model))
                        ss.chat.append({"role": "assistant", "content": reply})
                    except AssistantError as e:
                        ss.chat.pop()
                        st.error(str(e))
