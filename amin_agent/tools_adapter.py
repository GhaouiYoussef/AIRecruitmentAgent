"""Adapter for tools provided in the original repository.

This module attempts to import the real implementations from `agents.tools`.
If that fails, small stubs are provided so the package is runnable for tests.
"""

try:
    from agents.tools import (
        Candidate,
        linkedin_scraper,
        candidates_crawler,
        candidates_embedder,
        interview_question_generator,
        final_answer,
    )
except Exception:
    # Minimal stubs for local testing
    from typing import List

    from typing import Dict, Any, Optional


    class Candidate(dict):
        """Lightweight Candidate type backed by a dict."""
        def __init__(self, **kwargs):
            super().__init__(**kwargs)


    # Small in-memory candidate DB to make the tools slightly realistic.
    _CANDIDATE_DB = [
        Candidate(name="Alice Example", title="ML Engineer", skills=["python", "ml", "tensorflow"], years_experience=4, location="Paris", contact="alice@example.com"),
        Candidate(name="Bob Tester", title="Senior Software Engineer", skills=["python", "docker", "aws"], years_experience=7, location="Berlin", contact="bob@example.com"),
        Candidate(name="Carol Data", title="Data Scientist", skills=["python", "pandas", "ml", "sql"], years_experience=5, location="London", contact=None),
        Candidate(name="Dan ML", title="Machine Learning Engineer", skills=["python", "pytorch", "ml", "deployment"], years_experience=6, location="Remote", contact="dan@example.com"),
        Candidate(name="Eve Infra", title="DevOps Engineer", skills=["k8s", "docker", "terraform"], years_experience=4, location="Barcelona", contact=None),
    ]


    def _score_candidate(candidate: Dict[str, Any], tokens: list[str]) -> int:
        """Simple score: count of tokens found in name/title/skills."""
        text = " ".join([str(candidate.get(k, "")) for k in ("name", "title")]).lower()
        skills = " ".join(candidate.get("skills", [])).lower()
        score = 0
        for t in tokens:
            if t in text or t in skills:
                score += 1
        return score


    def linkedin_scraper(query: str, max_results: int = 5):
        """Return up to `max_results` candidates matching the query using
        simple substring matching over title and skills.
        """
        if not query:
            return []
        tokens = [t.strip().lower() for t in query.split() if t.strip()]
        scored = []
        for c in _CANDIDATE_DB:
            score = _score_candidate(c, tokens)
            if score > 0:
                scored.append((score, c))
        # sort by score desc then years_experience desc
        scored.sort(key=lambda x: (-x[0], -x[1].get("years_experience", 0)))
        return [c for _, c in scored][:max_results]


    def candidates_crawler(seed_urls: Optional[list] = None, limit: int = 10):
        """Pretend to crawl external sources — return the DB up to `limit`.

        This is a deterministic, local-only implementation used for testing.
        """
        return _CANDIDATE_DB[:limit]


    def candidates_embedder(candidates: list, method: str = "simple"):
        """Return a trivial numeric embedding per candidate.

        The embedding is a vector of length 3:
        [num_skills, years_experience, has_contact]
        """
        embeddings = []
        for c in candidates:
            num_skills = len(c.get("skills", []))
            years = float(c.get("years_experience", 0))
            has_contact = 1.0 if c.get("contact") else 0.0
            embeddings.append([num_skills, years, has_contact])
        return embeddings


    def interview_question_generator(candidate: Dict[str, Any], num_questions: int = 5):
        """Generate a small tailored list of interview questions based on skills.

        This produces deterministic, useful-looking questions for testing.
        """
        skills = candidate.get("skills", [])
        title = candidate.get("title", "Candidate")
        questions = []
        # opener
        questions.append(f"Tell me about your most impactful project as a {title}.")
        for s in skills[: max(0, num_questions - 2)]:
            questions.append(f"Describe a challenge you solved using {s} and what you learned.")
        # fallback to general question if not enough skills
        while len(questions) < num_questions:
            questions.append("How do you approach learning a new technology or tool?")
        return questions[:num_questions]


    def final_answer(candidates: list, role: str = "the role"):
        """Synthesize a compact human-facing final answer.

        Ranks candidates by simple heuristics and returns a structured dict
        containing short summaries and suggested next steps.
        The `candidates` argument may be a list, or a string (JSON or Python repr).
        """
        import json
        import ast

        # normalize candidates input
        parsed = []
        if isinstance(candidates, str):
            # try JSON, then Python literal eval, else empty
            try:
                parsed = json.loads(candidates)
            except Exception:
                try:
                    parsed = ast.literal_eval(candidates)
                except Exception:
                    parsed = []
        elif isinstance(candidates, list):
            parsed = candidates
        else:
            parsed = []

        # ensure parsed is a list of dict-like objects
        norm_candidates = []
        for item in parsed:
            if isinstance(item, dict):
                norm_candidates.append(item)
            else:
                # if item is a tuple or other, try to coerce
                try:
                    # attempt to form a minimal dict
                    name = getattr(item, "name", None) or (item[0] if isinstance(item, (list, tuple)) and item else None)
                    title = getattr(item, "title", None) or (item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else None)
                    norm_candidates.append({"name": name, "title": title})
                except Exception:
                    continue

        # compute a simple rank: more skills and contact preferred
        def rank_key(c):
            return (len(c.get("skills", [])), 1 if c.get("contact") else 0, c.get("years_experience", 0))

        ranked = sorted(norm_candidates, key=lambda c: rank_key(c), reverse=True)
        recs = []
        for c in ranked:
            recs.append({
                "name": c.get("name"),
                "title": c.get("title"),
                "skills": c.get("skills", []),
                "years_experience": c.get("years_experience"),
                "location": c.get("location"),
                "contact": c.get("contact"),
                "rationale": f"Matches skills: {', '.join(c.get('skills', [])[:3])}.",
            })

        next_steps = {
            "outreach_template": (
                "Hi {name},\n\nI came across your profile and think you'd be a great fit for {role}. "
                "Would you be open to a quick call to discuss?\n\nBest regards"
            ),
            "interview_questions": [
                "Intro: walk me through your background.",
                "Role fit: technical challenge related to key skills.",
                "Behavioral: teamwork/conflict resolution.",
            ],
        }

        return {"candidates": recs, "next_steps": next_steps, "notes": f"Searched for {role}."}


__all__ = [
    "Candidate",
    "linkedin_scraper",
    "candidates_crawler",
    "candidates_embedder",
    "interview_question_generator",
    "final_answer",
]
