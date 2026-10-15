"""Gemini-powered money assistant.

The assistant is stateless on the server side: every call sends the standing
rules, a fresh snapshot of the user's numbers, and the recent chat history.
"""
from __future__ import annotations

from typing import Iterator, Mapping, Sequence

DEFAULT_MODEL = "gemini-3.8-flash"
MAX_HISTORY = 12  # messages kept per request (user + assistant)

SYSTEM_RULES = """You are a friendly personal-finance assistant inside "Paisa Planner", \
a monthly budget and investing tool for people in India.

- Use rupees (₹) and Indian number style (lakh, crore).
- Be concrete: quote the user's own numbers and give rupee amounts.
- Topics you can cover: budgeting, emergency funds, SIPs in mutual fund categories \
(index funds, flexi-cap, mid/small-cap, ELSS, debt funds), PPF, NPS, gold ETFs, and \
sensible limits for direct stock investing.
- Do not recommend specific named stocks or promise returns. Treat return figures as assumptions.
- Mention tax rules only at a general level.
- Keep answers under about 250 words unless asked for more. Use short paragraphs, \
bullet points and **bold** for key figures.
- End with one short line noting this is general education, not SEBI-registered advice."""


class AssistantError(Exception):
    """Raised with a message that is safe to show to the user."""


def _friendly(err) -> str:
    code = getattr(err, "code", None)
    if code in (401, 403):
        return "Gemini rejected the API key. Check GEMINI_API_KEY."
    if code == 400 and "API key" in str(err):
        return "Gemini rejected the API key. Check GEMINI_API_KEY."
    if code == 404:
        return "That Gemini model isn't available to your key. Set GEMINI_MODEL to another model (e.g. gemini-3.5-flash-lite)."
    if code == 429:
        return "Gemini rate limit reached. Wait a minute and ask again."
    if code and code >= 500:
        return "Gemini is having trouble right now. Try again shortly."
    return f"Gemini request failed: {err}"


def build_contents(history: Sequence[Mapping[str, str]]):
    """Convert [{role, content}] chat history to Gemini Content objects."""
    from google.genai import types

    recent = list(history)[-MAX_HISTORY:]
    while recent and recent[0]["role"] != "user":  # Gemini wants a user turn first
        recent.pop(0)
    return [
        types.Content(
            role="user" if m["role"] == "user" else "model",
            parts=[types.Part.from_text(text=m["content"])],
        )
        for m in recent
    ]


def stream_reply(
    api_key: str,
    snapshot: str,
    history: Sequence[Mapping[str, str]],
    model: str = DEFAULT_MODEL,
) -> Iterator[str]:
    """Yield the assistant's reply in chunks as Gemini streams it."""
    from google import genai
    from google.genai import errors, types

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=f"{SYSTEM_RULES}\n\nTHE USER'S CURRENT NUMBERS:\n{snapshot}",
        temperature=0.4,
    )
    try:
        for chunk in client.models.generate_content_stream(
            model=model, contents=build_contents(history), config=config
        ):
            if chunk.text:
                yield chunk.text
    except errors.APIError as e:
        raise AssistantError(_friendly(e)) from e
