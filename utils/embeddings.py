# utils/embeddings.py

import os
import hashlib
import random

from dotenv import load_dotenv
import voyageai

# Load .env so VOYAGE_API_KEY is available
load_dotenv()

# ---- HARD-CODED VOYAGE CONFIG FOR HACKATHON ----
EMBEDDING_MODEL = "voyage-2"
EMBEDDING_DIM = 1024

# VOYAGE_API_KEY must be set in .env
_vo_client = voyageai.Client(api_key=os.getenv("VOYAGE_API_KEY"))


def _fake_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """
    Deterministic fake embedding if Voyage errors.
    Same text -> same vector, good enough for demo dedup.
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
    Get an embedding vector for the text using Voyage.
    Falls back to a deterministic fake embedding on error.
    """
    text = (text or "").strip()
    if not text:
        return [0.0] * EMBEDDING_DIM

    try:
        print(f"[embed_text] Using Voyage model={EMBEDDING_MODEL}, dim={EMBEDDING_DIM}")
        res = _vo_client.embed(
            [text],
            model=EMBEDDING_MODEL,
            input_type="document",
            output_dimension=EMBEDDING_DIM,
        )
        emb = res.embeddings[0]

        if len(emb) != EMBEDDING_DIM:
            print(
                f"[embed_text] Warning: got dim={len(emb)} but EMBEDDING_DIM={EMBEDDING_DIM}, using fake embedding."
            )
            return _fake_embedding(text)

        return emb

    except Exception as e:
        print("[embed_text] Voyage error, using fake embedding:", e)
        return _fake_embedding(text)
