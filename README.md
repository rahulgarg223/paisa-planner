# 💰 Paisa Planner

A monthly budget planner for India that turns your surplus into an investment plan, with a Gemini-powered assistant that answers questions using your own numbers.

![tests](https://github.com/rahulgarg223/paisa-planner/actions/workflows/tests.yml/badge.svg)

<!-- Add a screenshot after your first run: save it as docs/screenshot.png -->
<!-- ![Paisa Planner](docs/screenshot.png) -->

## Features

| Tab | What it does |
|---|---|
| **Budget** | Editable income and expense tables. Each expense gets a category and a Need/Want tag. Shows a live **50/30/20 check** and spending by category. Save and load your plan as JSON. |
| **SIP planner** | SIP growth with **annual step-up**, charted year by year. A goal calculator works out the monthly SIP needed for a target, **adjusted for inflation**. One click fills the SIP with your actual surplus. |
| **Allocation** | Suggests an equity/debt/gold split from your age, horizon and risk appetite, broken down into fund categories with ₹/month amounts. Checks your **emergency fund** first and routes part of the surplus there until it covers 6 months. |
| **AI assistant** | A chat on **Google Gemini**. Each question goes with a fresh snapshot of your budget, SIP and allocation, so answers quote your numbers. Includes starter prompts ("Where can I cut?", "Build my SIP plan"). |

All amounts use Indian formatting (₹12,34,567 · ₹25.00 L · ₹3.10 Cr).

## Quick start

```bash
git clone https://github.com/rahulgarg223/paisa-planner.git
cd paisa-planner
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

The app opens with example figures. Edit the tables or press **Start blank**.

### Turn on the AI assistant

1. Get a free API key from [Google AI Studio](https://aistudio.google.com/apikey).
2. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and paste in your key:

   ```toml
   GEMINI_API_KEY = "your-key-here"
   ```

You can also set `GEMINI_API_KEY` as an environment variable, or paste a key into the app (kept for that session only). `secrets.toml` is in `.gitignore`, so your key never gets committed.

The default model is `gemini-3.8-flash`. To use another one, set `GEMINI_MODEL` (for example `gemini-3.5-flash-lite` for faster, cheaper replies).

## Deploy for free

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io), click **Create app** and pick the repo, with `app.py` as the main file.
3. Under **Advanced settings → Secrets**, paste `GEMINI_API_KEY = "..."`.

If you'd rather not spend your own key's quota, leave the secret out. Visitors can then paste their own key.

## How the numbers work

- **SIP value**: money goes in at the start of each month and compounds monthly at `annual_return / 12`. With step-up, the monthly amount rises once a year.
- **Goal SIP**: the goal is first inflated to its future cost, `goal × (1 + inflation)^years`. The required SIP then comes from the annuity-due formula `FV / ((((1+r)^n − 1) / r) × (1+r))`.
- **Allocation**: equity starts at `100 − age`, adds 10 for aggressive or subtracts 15 for conservative, and is capped by horizon (under 3 yrs → 20%, under 5 → 50%, under 8 → 70%). It is clamped to 10–85% and rounded to 5. Gold is fixed at 10% and debt takes the rest. Equity is split into large-cap, flexi-cap and mid/small-cap by risk level.
- **Emergency fund**: the target is 6 × monthly expenses. While you're short, up to half the surplus goes there.

All of this lives in [`planner/finance.py`](planner/finance.py) as pure functions, separate from the UI, and is covered by tests.

## Project structure

```
paisa-planner/
├── app.py                  # Streamlit UI: tabs, tables, charts, chat
├── planner/
│   ├── finance.py          # Budget, SIP, goal, allocation and emergency-fund maths
│   └── ai.py               # Gemini streaming client and assistant prompt
├── tests/
│   ├── test_finance.py     # Unit tests for the maths
│   └── test_app.py         # Streamlit AppTest smoke tests (Gemini stubbed)
├── .streamlit/
│   ├── config.toml         # Theme
│   └── secrets.toml.example
└── .github/workflows/tests.yml
```

## Run the tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Tech stack

Python · Streamlit · pandas · Plotly · Google Gemini (`google-genai`) · pytest · GitHub Actions

## Disclaimer

Paisa Planner is an educational project. Return figures are assumptions, and nothing here is advice from a SEBI-registered investment adviser. Tax notes reflect FY 2025-26 rules. Check current rules before acting.

## License

MIT © Rahul Garg
