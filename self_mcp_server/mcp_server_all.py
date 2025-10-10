"""Unified MCP server exposing all candidate recruitment tools.

This aggregates:
  - Orchestrated LinkedIn pipeline (search -> extract -> optional score) via `linkedin_pipeline`
  - Low-level primitives separated out for finer control / graph composition:
        * candidate_search
        * extract_profiles
        * prepare_job_description
        * score_candidates (re-export / wrapper identical to legacy one)
  - Utility text tools (hashing, counting, substring)

Each MCP tool has a lightweight self-test executed when the module is run
with the environment variable RUN_SELF_TESTS=1 (default). To start ONLY the
server (skip tests) set RUN_SELF_TESTS=0.

Network-dependent tools (search / extract / score) provide test-mode flags
that avoid external calls enabling fast offline validation.
"""

from __future__ import annotations

from typing import Any, Iterable
from pathlib import Path
import hashlib
import os
import json
import sys
from loguru import logger
from mcp.server.fastmcp import FastMCP

# Ensure repo root (parent directory) is on sys.path so we can import sibling package
_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent
if str(_REPO_ROOT) not in sys.path:  # idempotent
    sys.path.insert(0, str(_REPO_ROOT))

# Import the existing tool module (contains orchestration + internals)
try:
    from ollama_recruiter import tools as recruiter_tools  # type: ignore
except ModuleNotFoundError as e:  # pragma: no cover - defensive
    raise ModuleNotFoundError(
        "Failed to import 'ollama_recruiter'. Confirm the repository root is the working directory or adjust PYTHONPATH."
    ) from e

mcp = FastMCP("ai-recruitment-suite")


# ---------------------------------------------------------------------------
# Helper / shared configuration
# ---------------------------------------------------------------------------
def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _tmp_json_dir() -> Path:
    d = _repo_root() / "Full system" / "tmp_candids_jsons"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# High-level orchestration tool (wrapper around existing linkedin_search_tool)
# ---------------------------------------------------------------------------
@mcp.tool()
def linkedin_pipeline(
    query: str,
    num_candidates: int = 5,
    test_mode_extract: bool = False,
    test_mode_score: bool = False,
) -> dict | list[str]:
    """Run the full candidate pipeline (search, extract, optionally score).

    Returns either a mapping (when scoring succeeds) or a list of links.
    Set `test_mode_extract=True` for deterministic small link list & still
    exercise extraction; set `test_mode_score=True` to skip extraction+scoring
    network calls (returns links only).
    """
    logger.info(
        f"linkedin_pipeline: query='{query}' num={num_candidates} test_extract={test_mode_extract} test_score={test_mode_score}"
    )
    return recruiter_tools.linkedin_search_tool(
        query=query,
        num_candidates=num_candidates,
        test_mode_extract=test_mode_extract,
        test_mode_score=test_mode_score,
    )


# ---------------------------------------------------------------------------
# Low-level primitives (wrapping internal underscore functions). Useful when
# a client wants to build a custom LangGraph / workflow.
# ---------------------------------------------------------------------------
@mcp.tool()
def candidate_search(
    query: str,
    num_candidates: int = 5,
    test_mode_extract: bool = False,
) -> list[str]:
    """Search for candidate profile links only (no extraction or scoring)."""
    requests = recruiter_tools._import_requests()
    if requests is None:
        return recruiter_tools.FALLBACK_LINKS
    search_url = os.getenv("LINKEDIN_SEARCH_URL", "http://127.0.0.1:8000/search")
    links = recruiter_tools._search_candidates(
        requests, search_url, query, num_candidates, test_mode_extract
    )
    logger.info(f"candidate_search: returned {len(links)} links")
    return links


@mcp.tool()
def extract_profiles(
    links: list[str],
    test_mode_score: bool = False,
    test_mode_extract: bool = False,
) -> list[str]:
    """Extract profile JSON for provided links; returns saved file paths.

    Use test_mode_score=True to skip extraction entirely (mirrors orchestrator).
    """
    requests = recruiter_tools._import_requests()
    if requests is None:
        return []
    extraction_base = os.getenv("LINKEDIN_EXTRACT_URL", "http://127.0.0.1:8000/extract")
    out_dir = _tmp_json_dir()
    saved = recruiter_tools._extract_and_save_profiles(
        requests,
        links,
        extraction_base,
        out_dir,
        test_mode_score=test_mode_score,
        test_mode_extract=test_mode_extract,
    )
    logger.info(f"extract_profiles: saved {len(saved)} files to {out_dir}")
    return saved


@mcp.tool()
def prepare_job_description() -> dict[str, str | None]:
    """Return job description text and original file path (if any)."""
    job_text, job_file = recruiter_tools._prepare_job_description(_repo_root())
    return {"job_text": job_text, "original_file": str(job_file) if job_file else None}


@mcp.tool()
def score_candidates(
    scorer_url: str,
    out_dir: str | Path | None = None,
    job_text: str | None = None,
) -> dict[str, float] | None:
    """Score already extracted profiles located in `out_dir`.

    Parameters:
        scorer_url: Base URL of scoring service (without trailing slash path).
        out_dir: Directory containing candidate JSON files (defaults to tmp dir).
        job_text: Job description; if None we load prepared description.
    """
    requests = recruiter_tools._import_requests()
    if requests is None:
        logger.error("requests not available; cannot score")
        return None
    out_dir_path = Path(out_dir) if out_dir else _tmp_json_dir()
    if job_text is None:
        job_text, _ = recruiter_tools._prepare_job_description(_repo_root())
    if not job_text:
        logger.error("No job text available for scoring")
        return None
    logger.info(f"score_candidates: scoring {len(list(out_dir_path.glob('*.json')))} profiles")
    return recruiter_tools._score_candidates(requests, scorer_url, out_dir_path, job_text)


# ---------------------------------------------------------------------------
# Utility / text tools (re-exported from legacy server with identical behavior)
# ---------------------------------------------------------------------------
@mcp.tool()
def generate_md5_hash(input_str: str) -> str:
    """Return MD5 hex digest of the input string."""
    logger.info(f"generate_md5_hash: hashing {len(input_str)} chars")
    md5_hash = hashlib.md5()
    md5_hash.update(input_str.encode("utf-8"))
    return md5_hash.hexdigest()


@mcp.tool()
def count_characters(input_str: str) -> int:
    """Count characters in a string."""
    logger.info("count_characters invoked")
    return len(input_str)


@mcp.tool()
def get_first_half(input_str: str) -> str:
    """Return first half of the string (floor divide)."""
    logger.info("get_first_half invoked")
    midpoint = len(input_str) // 2
    return input_str[:midpoint]


# ---------------------------------------------------------------------------
# Self-test harness
# ---------------------------------------------------------------------------
def _self_tests():  # pragma: no cover - runtime quick checks
    print("--- SELF TESTS (mcp_server_all) ---")
    # Deterministic pipeline test (skip external scoring, deterministic search list)
    pipeline_links = linkedin_pipeline(
        query="python backend", num_candidates=3, test_mode_extract=True, test_mode_score=True
    )
    print("linkedin_pipeline (test modes) ->", pipeline_links)

    # Low-level search
    links = candidate_search("data engineer", num_candidates=2, test_mode_extract=True)
    print("candidate_search ->", links)

    # Extraction (will likely attempt local extraction service; may save zero if unavailable)
    extracted = extract_profiles(links, test_mode_score=False, test_mode_extract=True)
    print("extract_profiles saved ->", extracted)

    # Job description
    jd = prepare_job_description()
    print("prepare_job_description ->", {k: (v[:60] + "...") if v and k == "job_text" else v for k, v in jd.items()})

    # Utilities
    print("generate_md5_hash('hello') ->", generate_md5_hash("hello"))
    print("count_characters('abc') ->", count_characters("abc"))
    print("get_first_half('abcdef') ->", get_first_half("abcdef"))

    # Scoring (expected to fail gracefully offline unless service running)
    if jd.get("job_text"):
        scores = score_candidates(
            scorer_url=os.getenv("CANDIDATE_SCORER_URL", "http://localhost:8001/scorer_tool"),
            out_dir=_tmp_json_dir(),
            job_text=jd.get("job_text") or "",
        )
        print("score_candidates ->", scores if scores is not None else "(None / unavailable)")
    print("--- END SELF TESTS ---")


if __name__ == "__main__":
    run_tests = os.getenv("RUN_SELF_TESTS", "1").lower() not in {"0", "false", "no"}
    if run_tests:
        _self_tests()
    logger.info(
        "Starting unified MCP server 'ai-recruitment-suite' over stdio. Set RUN_SELF_TESTS=0 to skip tests."
    )
    mcp.run(transport="stdio")
