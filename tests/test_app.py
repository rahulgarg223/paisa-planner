"""Smoke test: the Streamlit app renders every tab without errors."""
from streamlit.testing.v1 import AppTest


def test_app_renders_with_example_data():
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Income / month" in labels and "Surplus to invest" in labels
    income = next(m for m in at.metric if m.label == "Income / month")
    assert income.value == "₹73,000"


def test_use_surplus_button_sets_sip():
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    btn = next(b for b in at.button if b.label.startswith("Use my surplus"))
    btn.click().run()
    assert at.session_state.sip_amt == 31500  # ₹31,600 surplus rounded down to ₹500


def test_assistant_streams_reply(monkeypatch):
    import planner.ai as ai

    def fake_stream(api_key, snapshot, history, model=ai.DEFAULT_MODEL):
        assert "MONTHLY INCOME" in snapshot and history[-1]["role"] == "user"
        yield "Your savings rate "
        yield "is **43%**."

    monkeypatch.setattr(ai, "stream_reply", fake_stream)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    at = AppTest.from_file("../app.py", default_timeout=30).run()
    at.chat_input[0].set_value("How am I doing?").run()
    assert not at.exception
    assert at.session_state.chat[-1] == {"role": "assistant", "content": "Your savings rate is **43%**."}


def test_build_contents_starts_with_user_turn():
    from planner.ai import build_contents

    contents = build_contents([
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "q2"},
    ])
    assert [c.role for c in contents] == ["user", "model", "user"]
