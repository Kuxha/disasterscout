# utils/embeddings.py

import os
import hashlib
import random

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIError

load_dotenv()

# Official embedding model + dimension for this project
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
# text-embedding-3-small has 1536 dimensions
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1536"))

_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _fake_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """
    Deterministic fake embedding when we hit quota or API errors.
    Same text -> same vector, so dedup still kind of works for the demo.
    """
    text = (text or "").strip()
    if not text:
        return [0.0] * dim

    h = hashlib.sha256(text.encode("utf-8")).hexdigest()
    seed = int(h[:16], 16)
    rng = random.Random(seed)
    return [rng.uniform(-0.1, 0.1) for _ in range(dim)]


def embed_text(text: str) -> list[float]:
    """
    Get an embedding vector for the text.
    Falls back to fake embeddings on quota / API errors.
    """
    text = (text or "").strip()
    if not text:
        return [0.0] * EMBEDDING_DIM

    try:
        resp = _client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return resp.data[0].embedding

    except RateLimitError as e:
        print("[embed_text] RateLimitError, using fake embedding:", e)
        return _fake_embedding(text)

    except APIError as e:
        print("[embed_text] APIError, using fake embedding:", e)
        return _fake_embedding(text)

    except Exception as e:
        print("[embed_text] Unexpected error, using fake embedding:", e)
        return _fake_embedding(text)
