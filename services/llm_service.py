"""
LLM Service — Google Gemini integration via REST API.

Uses the Gemini REST API directly (no SDK needed) so it works on
any Python version. Provides natural-language answers for queries
that don't match any deterministic intent.
"""
import os
import json
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

SYSTEM_PROMPT = (
    "You are the Skylark Drone Operations Coordinator AI assistant. "
    "You help manage pilot rosters, drone fleets, mission assignments, "
    "conflict detection, and urgent reassignments for a drone survey company. "
    "Answer questions concisely and helpfully. Use markdown formatting. "
    "If the user seems to want a specific action (assign, conflict check, etc.), "
    "suggest the exact command they should type, such as:\n"
    "- `Show available pilots in Bangalore`\n"
    "- `Assign best pilot and drone to PRJ001`\n"
    "- `Check for conflicts`\n"
    "- `Urgent reassignment for PRJ002`\n"
    "- `Mark Arjun as On Leave`"
)


def ask_llm(user_message: str, context: str = "") -> Optional[str]:
    """
    Send a message to Gemini via REST API with optional drone-ops context.

    Returns the LLM response text, or None if LLM is unavailable.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None

    try:
        import requests
    except ImportError:
        logger.warning("requests library not available for LLM calls.")
        return None

    # Build the prompt
    parts = [{"text": SYSTEM_PROMPT + "\n\n"}]
    if context:
        parts.append({"text": "Current operations state:\n" + context + "\n\n"})
    parts.append({"text": "User question: " + user_message})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 500,
        },
    }

    try:
        resp = requests.post(
            GEMINI_API_URL,
            params={"key": api_key},
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract text from response
        candidates = data.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            text_parts = content.get("parts", [])
            if text_parts:
                return text_parts[0].get("text", "")

        return None
    except Exception as e:
        logger.warning("Gemini API error: %s", e)
        return None
