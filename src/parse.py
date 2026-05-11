"""Parse a WeChat screenshot into structured intent JSON via OpenAI-compatible vision API.

Configured via env: OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_VISION_MODEL.
Defaults route to flatkey.ai. Any OpenAI-compatible endpoint that supports vision works.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

from openai import OpenAI

SYSTEM = """You read a WeChat chat screenshot between the user (Hunter, sending green-bubble messages on the right) and one contact (gray-bubble messages on the left, with the contact's name in the header).

Extract a meeting-request intent as strict JSON. Schema:
{
  "contact_name": str,            // header name, e.g. "Mason 林辉"
  "contact_email": str | null,    // any email the contact provided in the chat
  "contact_city": str | null,     // city/region where the contact is located, mentioned by EITHER side (e.g. "纽约" / "NY")
  "contact_tz": str | null,       // best-guess IANA timezone for that city, e.g. "America/New_York". Default to "Asia/Shanghai" if no location signal at all.
  "intent": "meeting" | "other",  // is the contact asking to schedule a meeting?
  "meeting_mode": "online" | "offline" | "unspecified",
  "proposed_time": str | null,    // any specific time the contact proposed, ISO if possible, else verbatim
  "language": "zh" | "en" | "mixed",
  "summary": str                  // one-sentence description of what they want
}

Return ONLY the JSON object, no prose, no markdown fences."""


def _client() -> OpenAI:
    return OpenAI(
        base_url=os.environ.get("OPENAI_BASE_URL"),
        api_key=os.environ["OPENAI_API_KEY"],
    )


def parse_screenshot(image_path: str) -> dict:
    img = Path(image_path).read_bytes()
    media_type = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
    b64 = base64.standard_b64encode(img).decode()
    data_url = f"data:{media_type};base64,{b64}"

    model = os.environ.get("OPENAI_VISION_MODEL", "gpt-5.4")
    resp = _client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Parse this WeChat chat. Return JSON only."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            },
        ],
        response_format={"type": "json_object"},
    )
    text = resp.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].lstrip("json").strip()
    return json.loads(text)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: parse.py <screenshot.png>", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(parse_screenshot(sys.argv[1]), ensure_ascii=False, indent=2))
