"""MCP server exposing separate recruitment tools (no monolithic pipeline).

Tools exposed for agent planning:
- candidate_search(query, num_candidates=5, test_mode_extract=False) -> list[str]
- extract_profiles(links, test_mode_score=False, test_mode_extract=False) -> list[str]
- prepare_job_description() -> { job_text: str|None, original_file: str|None }
- score_candidates(scorer_url?, out_dir?, job_text) -> dict[str,float] | None

Ordering guidance for agents:
1) candidate_search -> 2) extract_profiles -> 3) prepare_job_description -> 4) score_candidates
"""

from __future__ import annotations
from pydantic import BaseModel

class SearchResponse(BaseModel):
    query: str
    num_candidates: int
    links: list[str]
    count: int
import os
from pathlib import Path
from mcp.server.fastmcp import FastMCP
import asyncio
try:
    from loguru import logger  # type: ignore
except Exception:  # pragma: no cover - fallback when loguru isn't available
    class _DummyLogger:
        def info(self, msg: str):
            print(msg)

    logger = _DummyLogger()

# Ensure repo root import
_THIS = Path(__file__).resolve()
_REPO_ROOT = _THIS.parent.parent
import sys

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from ollama_recruiter import tools_separate as tools
except Exception as e:  # pragma: no cover
    raise RuntimeError(f"Failed to import tools_separate: {e}")


mcp = FastMCP("ai-recruitment-suite-separate",
)


@mcp.tool()
async def candidate_search(query: str, num_candidates: int = 5, test_mode_extract: bool = False) -> list[str]:
    return await asyncio.to_thread(
        tools.candidate_search, query=query, num_candidates=num_candidates, test_mode_extract=test_mode_extract
    )


@mcp.tool()
async def extract_profiles(links: list[str], test_mode_score: bool = False, test_mode_extract: bool = False) -> tuple[list[str], list[dict]]:
    return await asyncio.to_thread(
        tools.extract_profiles, links=links, test_mode_score=test_mode_score, test_mode_extract=test_mode_extract
    )


@mcp.tool()
async def prepare_job_description() -> dict[str, str | None]:
    return await asyncio.to_thread(tools.prepare_job_description)


@mcp.tool()
async def score_candidates(
    # scorer_url: str | None = None,
    # out_dir: str | None = None,
    job_text: str | None = None,
) -> dict[str, float] | None:
    return await asyncio.to_thread(tools.score_candidates, job_text=job_text)


# # Utility re-exports
# @mcp.tool()
# async def generate_md5_hash(input_str: str) -> str:
#     return await asyncio.to_thread(tools.generate_md5_hash, input_str)


# @mcp.tool()
# async def count_characters(input_str: str) -> int:
#     return await asyncio.to_thread(tools.count_characters, input_str)


# @mcp.tool()
# async def get_first_half(input_str: str) -> str:
#     return await asyncio.to_thread(tools.get_first_half, input_str)


def _self_tests():  # pragma: no cover
    print("--- SELF TESTS (mcp_server_separate) ---")
    # run sync for self-tests by directly calling underlying tools
    links = tools.candidate_search("python backend", num_candidates=2, test_mode_extract=True)
    print("candidate_search ->", links)
    saved = tools.extract_profiles(links, test_mode_score=False, test_mode_extract=True)
    print("extract_profiles ->", saved)
    jd = tools.prepare_job_description()
    print("prepare_job_description ->", {k: (v[:60] + "...") if v and k == "job_text" else v for k, v in jd.items()})
    if jd.get("job_text"):
        sc = tools.score_candidates(job_text=jd["job_text"])  # will only succeed if scorer is running
        print("score_candidates ->", sc if sc is None else {k: v for k, v in list(sc.items())[:3]})
    print("--- END SELF TESTS ---")


if __name__ == "__main__":
    # run_tests = os.getenv("RUN_SELF_TESTS", "1").lower() not in {"0", "false", "no"}
    # if run_tests:
    #     _self_tests()
    from loguru import logger
    logger.info("Starting MCP server 'ai-recruitment-suite-separate' over stdio")
    mcp.run(transport="stdio")
