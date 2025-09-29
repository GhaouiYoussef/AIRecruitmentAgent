"""Agents tools placeholders

This module provides placeholder implementations for tools referenced by the
notebook: linkedin_scraper, candidates_embedder, candidates_crawler, and
interview_question_generator. They are intentionally lightweight and documented
so you can replace the internals with real implementations (APIs, scraping,
embedding pipelines, etc.).
"""
from typing import List, Dict
from pydantic import BaseModel


class Candidate(BaseModel):
    name: str
    title: str
    summary: str
    profile_url: str | None = None


def linkedin_scraper(query: str, max_results: int = 5) -> List[Candidate]:
    """Placeholder LinkedIn scraper.

    Replace the internals with an API call or a web-scraping routine. Return
    a list of Candidate objects.
    """
    # TODO: implement real scraping / API
    sample = [
        Candidate(
            name="Alice Johnson",
            title="Software Engineer — Python / ML",
            summary="Experienced engineer with ML and backend experience.",
            profile_url="https://linkedin.example/alice",
        ),
        Candidate(
            name="Bob Smith",
            title="Senior ML Engineer",
            summary="Worked on production ML pipelines and data infra.",
            profile_url="https://linkedin.example/bob",
        ),
    ]
    return sample[:max_results]


def candidates_crawler(candidates: List[Candidate]) -> List[Candidate]:
    """Optional crawler to enrich candidate records.

    This can follow profile links, fetch additional text (blogs, github), and
    return an expanded list of Candidate objects with enriched `summary` fields.
    """
    # TODO: implement enrichment fetching
    enriched = []
    for c in candidates:
        enriched.append(c.copy())
    return enriched


def candidates_embedder(candidates: List[Candidate], model: str = "local") -> List[Dict]:
    """Convert candidate records into embeddings.

    Returns a list of dicts containing {"id", "embedding", "meta"} where
    "embedding" is a list[float]. This is a placeholder — plug in your
    embedding model or service and persist to a vector DB if desired.
    """
    # TODO: replace with real embeddings
    results = []
    for idx, c in enumerate(candidates):
        results.append({
            "id": f"candidate-{idx}",
            "embedding": [0.0] * 768,  # dummy vector
            "meta": c.dict(),
        })
    return results


def interview_question_generator(candidate: Candidate, role_description: str) -> List[str]:
    """Generate interview questions tailored to the candidate and role.

    Replace with an LLM call if you want high-quality prompts. For now this
    returns a small set of templated questions.
    """
    q = [
        f"Explain a project where you built an ML pipeline end-to-end, focusing on {candidate.title}.",
        "How do you monitor model performance in production?",
        "Describe a time you optimized model inference latency.",
    ]
    return q


__all__ = [
    "Candidate",
    "linkedin_scraper",
    "candidates_crawler",
    "candidates_embedder",
    "interview_question_generator",
]
