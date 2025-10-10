from __future__ import annotations

"""Thin wrappers exposing the LinkedIn pipeline as separate, agent-plannable tools.

These functions reuse the internal helpers in `ollama_recruiter.tools` to avoid
code duplication while presenting clean, single-responsibility entry points.

Order constraints for callers (recommended):
- candidate_search -> extract_profiles -> prepare_job_description -> score_candidates
  * extract_profiles requires a non-empty list of profile links
  * score_candidates requires available extracted JSONs and a job description text

Environment variables respected:
- LINKEDIN_SEARCH_URL (default: http://127.0.0.1:8000/search)
- LINKEDIN_EXTRACT_URL (default: http://127.0.0.1:8000/extract)
- CANDIDATE_SCORER_URL (default: http://localhost:8001/scorer_tool)
"""

from pathlib import Path
import os
from typing import Any

# Reuse existing internals
from .tools import (
    _import_requests,
    _repo_root,
    _search_candidates,
    _extract_and_save_profiles,
    _prepare_job_description,
    _score_candidates,
    FALLBACK_LINKS,
)


def _tmp_json_dir(repo_root: Path | None = None) -> Path:
    root = repo_root or _repo_root()
    d = root / "Full system" / "tmp_candids_jsons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def candidate_search(
    query: str,
    num_candidates: int = 5,
    test_mode_extract: bool = False,
) -> list[str]:
    """Search for candidate profile links only (no extraction or scoring)."""
    requests = _import_requests()
    if requests is None:
        # In absence of requests, use fallback; test mode keeps deterministic subset via helper
        if test_mode_extract:
            return [
                "https://www.linkedin.com/in/saber-chadded-36552b192/",
                "https://www.linkedin.com/in/guesmi-wejden-5269222aa/",
            ]
        return FALLBACK_LINKS

    search_url = os.getenv("LINKEDIN_SEARCH_URL", "http://127.0.0.1:8000/search")
    return _search_candidates(requests, search_url, query, num_candidates, test_mode_extract)


def extract_profiles(
    links: list[str],
    test_mode_score: bool = False,
    test_mode_extract: bool = False,
) -> list[str]:
    """Extract LinkedIn profiles and save JSON locally. Returns saved file paths."""
    if not links:
        return []

    requests = _import_requests()
    if requests is None:
        # Cannot perform HTTP extraction without requests
        return []

    repo_root = _repo_root()
    out_dir = _tmp_json_dir(repo_root)
    extract_url = os.getenv("LINKEDIN_EXTRACT_URL", "http://127.0.0.1:8000/extract")
    return _extract_and_save_profiles(
        requests, links, extract_url, out_dir, test_mode_score, test_mode_extract
    )


def prepare_job_description() -> dict[str, str | None]:
    """Read and stabilize the job description file.

    Returns dict with keys:
      - job_text: str | None
      - original_file: str | None (path)
    """
    repo_root = _repo_root()
    job_text, job_file_path = _prepare_job_description(repo_root)
    return {
        "job_text": job_text,
        "original_file": str(job_file_path) if job_file_path else None,
    }


def score_candidates(
    # scorer_url: str | None = None,
    # out_dir: str | Path | None = None,
    job_text: str | None = None,
) -> dict[str, float] | None:
    """Score previously extracted profiles against a provided job description text.

    - scorer_url: override scoring service base (defaults to CANDIDATE_SCORER_URL)
    - out_dir: folder containing extracted candidate JSON files (defaults to tmp path)
    - job_text: REQUIRED job description text
    """

    repo_root = _repo_root()

    jd_dir = repo_root / "ollama_recruiter" / "data" / "jd_input"

    if not job_text and not jd_dir.exists():
        return None

    requests = _import_requests()
    if requests is None:
        return None

    
    # out_path = Path(out_dir) if out_dir else _tmp_json_dir(repo_root)
    # base_url = scorer_url or os.getenv("CANDIDATE_SCORER_URL", "http://localhost:8001/scorer_tool")
    return _score_candidates(requests, repo_root, job_text)


# Optional small utilities for parity with previous servers
def generate_md5_hash(input_str: str) -> str:
    import hashlib

    return hashlib.md5(input_str.encode("utf-8")).hexdigest()


def count_characters(input_str: str) -> int:
    return len(input_str)


def get_first_half(input_str: str) -> str:
    mid = len(input_str) // 2
    return input_str[:mid]
