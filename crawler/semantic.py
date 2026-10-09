"""
Lightweight NLP helpers for the scorer: stemming and tokenization.

Degrades gracefully: if nltk is unavailable a simple suffix stripper is used.
"""

import functools
import logging
import re
from typing import Set

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
