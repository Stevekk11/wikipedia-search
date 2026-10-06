"""
Lightweight NLP helpers for the scorer: stemming and optional local embeddings.

Both features degrade gracefully: if nltk is unavailable a simple suffix stripper is
used, and if sentence-transformers is unavailable (or WIKI_EMBEDDINGS=0) the
embedding similarity is skipped (returns None).
"""

import functools
import logging
import os
import re
from typing import Dict, Optional, Set

logger = logging.getLogger("wikipedia_crawler.semantic")

# ---------------------------------------------------------------------------
# Stemming
# ---------------------------------------------------------------------------
try:  # pragma: no cover - depends on environment
    from nltk.stem.snowball import SnowballStemmer

    _STEMMER = SnowballStemmer("english")
except Exception:  # pragma: no cover
    _STEMMER = None

# Irregular demonyms/country forms that stemmers cannot unify on their own.
_IRREGULAR = {
    "poles": "pol",
    "polish": "pol",
    "poland": "pol",
}


def _fallback_stem(word: str) -> str:
    for suffix in ("ings", "ing", "ies", "ers", "er", "ed", "es", "s", "ish", "ian", "an", "ic", "al"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


@functools.lru_cache(maxsize=50000)
def stem(word: str) -> str:
    """Return a normalized stem for a lowercase word."""
    if word in _IRREGULAR:
        return _IRREGULAR[word]
    if _STEMMER is not None:
        return _STEMMER.stem(word)
    return _fallback_stem(word)


def stem_tokens(text: str) -> Set[str]:
    """Tokenize text and return the set of stemmed word tokens."""
    return {stem(t) for t in re.findall(r"\w+", text.lower())}


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------
_MODEL_NAME = "all-MiniLM-L6-v2"
_model = None
_model_failed = False
_embedding_cache: Dict[str, object] = {}


def embeddings_enabled() -> bool:
    return os.environ.get("WIKI_EMBEDDINGS", "1") != "0" and not _model_failed


def _get_model():
    global _model, _model_failed
    if _model is not None or _model_failed:
        return _model
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(_MODEL_NAME)
    except Exception as exc:
        _model_failed = True
        logger.info(f"Embedding model unavailable, falling back to lexical scoring: {exc}")
    return _model


def _embed(text: str):
    cached = _embedding_cache.get(text)
    if cached is not None:
        return cached
    model = _get_model()
    if model is None:
        return None
    vec = model.encode(text, normalize_embeddings=True)
    if len(_embedding_cache) > 20000:
        _embedding_cache.clear()
    _embedding_cache[text] = vec
    return vec


def cosine_similarity(text_a: str, text_b: str) -> Optional[float]:
    """Cosine similarity between two texts, or None when embeddings are unavailable."""
    if not embeddings_enabled() or not text_a or not text_b:
        return None
    a, b = _embed(text_a), _embed(text_b)
    if a is None or b is None:
        return None
    return float(sum(float(x) * float(y) for x, y in zip(a, b)))


def warm_up() -> bool:
    """Load the model (blocking). Returns True if embeddings are usable."""
    return embeddings_enabled() and _get_model() is not None


def prime_embeddings(texts) -> None:
    """Batch-encode texts into the cache (~1ms/text vs ~20ms one-by-one)."""
    if not embeddings_enabled():
        return
    model = _get_model()
    if model is None:
        return
    todo = list({t for t in texts if t and t not in _embedding_cache})
    if not todo:
        return
    if len(_embedding_cache) + len(todo) > 20000:
        _embedding_cache.clear()
    for t, vec in zip(todo, model.encode(todo, batch_size=64, normalize_embeddings=True)):
        _embedding_cache[t] = vec
