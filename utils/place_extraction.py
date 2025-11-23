# utils/place_extraction.py
import json
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM = """
Extract the most specific geographic place mentioned in this text.
Return ONLY valid JSON.

Examples:
"Flooding hits Bay Ridge, Brooklyn" →
{"place": "Bay Ridge, Brooklyn, NY", "confidence": 0.95}

"Storm affects lower Manhattan" →
{"place": "Lower Manhattan, New York, NY", "confidence": 0.92}

If no place found: {"place": null, "confidence": 0}
"""

def extract_place_from_text(text: str) -> str | None:
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": text},
            ],
            max_tokens=200,
            temperature=0
        )
        
        raw = resp.choices[0].message.content
        data = json.loads(raw)

        return data.get("place")
    except Exception as e:
        print("[extract_place] error:", e)
        return None
