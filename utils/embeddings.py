# utils/embeddings.py

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

EMBEDDING_MODEL = "text-embedding-3-large"  # 1536 dims

def embed_text(text: str) -> list[float]:
    text = text.strip()
    if not text:
        return []
    resp = _client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return resp.data[0].embedding
