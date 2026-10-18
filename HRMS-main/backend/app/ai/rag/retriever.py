import math
import re
from collections import Counter
from dataclasses import dataclass

from app.ai.rag.chunker import PolicyChunk, chunk_policies
from app.models.hr_policy import HRPolicy


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_STOP_WORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
    "for", "from", "how", "i", "in", "is", "it", "me", "of", "on", "or", "our",
    "please", "the", "their", "there", "they", "to", "us", "what", "when", "where",
    "which", "who", "why", "with", "you", "your", "employee", "employees", "policy",
    "working", "work", "company",
}


@dataclass(frozen=True)
class PolicyMatch:
    chunk: PolicyChunk
    score: float


def retrieve_policy_chunks(question: str, policies: list[HRPolicy], limit: int = 4) -> list[PolicyMatch]:
    chunks = chunk_policies(policies)
    if not chunks:
        return []

    corpus_tokens = [
        _terms(f"{chunk.title} {chunk.category} {chunk.section} {chunk.text}")
        for chunk in chunks
    ]
    query_tokens = _terms(question)
    if not query_tokens:
        return []

    document_frequency: Counter[str] = Counter()
    for terms in corpus_tokens:
        document_frequency.update(set(terms))

    query_vector = _tfidf(query_tokens, document_frequency, len(chunks))
    if not query_vector:
        return []

    matches: list[PolicyMatch] = []
    for chunk, terms in zip(chunks, corpus_tokens):
        vector = _tfidf(terms, document_frequency, len(chunks))
        score = _cosine_similarity(query_vector, vector)
        if score > 0:
            matches.append(PolicyMatch(chunk=chunk, score=score))

    matches.sort(key=lambda match: match.score, reverse=True)
    return matches[:limit]


def _terms(text: str) -> list[str]:
    normalized: list[str] = []
    for token in _TOKEN_PATTERN.findall(text.lower()):
        if token in _STOP_WORDS:
            continue
        if len(token) > 4 and token.endswith("ies"):
            token = f"{token[:-3]}y"
        elif len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        normalized.append(token)

    bigrams = [f"{left}_{right}" for left, right in zip(normalized, normalized[1:])]
    return normalized + bigrams


def _tfidf(terms: list[str], document_frequency: Counter[str], document_count: int) -> dict[str, float]:
    frequencies = Counter(terms)
    vector = {
        term: (1.0 + math.log(count))
        * (math.log((document_count + 1) / (document_frequency[term] + 1)) + 1.0)
        for term, count in frequencies.items()
    }
    magnitude = math.sqrt(sum(value * value for value in vector.values()))
    if magnitude == 0:
        return {}
    return {term: value / magnitude for term, value in vector.items()}


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    smaller, larger = (left, right) if len(left) < len(right) else (right, left)
    return sum(value * larger.get(term, 0.0) for term, value in smaller.items())
