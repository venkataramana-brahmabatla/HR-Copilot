from dataclasses import dataclass
import re

from app.models.hr_policy import HRPolicy
from app.ai.rag.loader import load_policy_sections


@dataclass(frozen=True)
class PolicyChunk:
    policy_id: int
    title: str
    category: str
    section: str
    text: str


def chunk_policies(policies: list[HRPolicy], max_words: int = 320, overlap_words: int = 50) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    for policy in policies:
        for section, text in load_policy_sections(policy):
            words = re.findall(r"\S+", text)
            if not words:
                continue

            start = 0
            while start < len(words):
                end = min(start + max_words, len(words))
                excerpt = " ".join(words[start:end]).strip()
                if excerpt:
                    chunks.append(
                        PolicyChunk(
                            policy_id=policy.id,
                            title=policy.title,
                            category=policy.category,
                            section=section,
                            text=excerpt,
                        )
                    )
                if end == len(words):
                    break
                start = end - overlap_words

    return chunks
