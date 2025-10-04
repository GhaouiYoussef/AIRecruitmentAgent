import json
import shutil
import os
from pathlib import Path

# -------------------------------------------------------------
# Global flag (user controlled): can be toggled either by editing this variable
# or by setting environment variable CLEANUP_AND_ARCHIVE to 1/true/yes.
# When enabled (True) AFTER a successful scoring run we will:
#  1. Move the ORIGINAL job description file that was discovered (not the stabilized copy) into
#     jd_history with a timestamped filename (leaving the stable job_description.txt in place).
#  2. Delete all temporary candidate JSON profile files under Full system/tmp_candids_jsons.
# Default is False to preserve artifacts for inspection.
# -------------------------------------------------------------
CLEANUP_AND_ARCHIVE = os.getenv("CLEANUP_AND_ARCHIVE", "0").lower() in {"1", "true", "yes", "y"}

# Fallback links used when requests is missing or remote calls fail early.
FALLBACK_LINKS = [
    "https://www.linkedin.com/in/saber-chadded-36552b192/",
    "https://www.linkedin.com/in/guesmi-wejden-5269222aa/",
    "https://www.linkedin.com/in/hichem-dridi/",
    "https://www.linkedin.com/in/nour-hamdi/",
    "https://www.linkedin.com/in/iyadh-chaouch-072077225/",
]


def _import_requests():
    """Local import helper so module import does not hard‑fail if requests missing."""
    try:
        import requests  # type: ignore
        return requests
    except Exception as e:  # pragma: no cover - defensive
        print(f"linkedin_search_tool: 'requests' not available: {e}; using fallback links")
        return None


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _search_candidates(requests, service_url: str, query: str, num_candidates: int, test_mode_extract: bool) -> list[str]:
    """Call the external search service (unless test_mode_extract) and return list of profile links.

    In test mode a fixed subset of links is returned.
    """
    if test_mode_extract:
        return [
            "https://www.linkedin.com/in/saber-chadded-36552b192/",
            "https://www.linkedin.com/in/guesmi-wejden-5269222aa/",
        ]
    try:
        resp = requests.get(
            service_url,
            params={"query": query, "num_candidates": int(num_candidates)},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        links = None
        if isinstance(data, dict):
            links = data.get("links") or data.get("results") or data.get("candidates")
        if not links or not isinstance(links, list):
            raise ValueError(f"Unexpected response shape: {data}")
        return links
    except Exception as e:
        print(f"Search failed ({e}); using fallback links")
        return FALLBACK_LINKS


def _extract_and_save_profiles(requests, links: list[str], extraction_base: str, out_dir: Path, test_mode_score: bool, test_mode_extract: bool) -> list[str]:
    """Extract each LinkedIn profile via extraction service and save JSON locally.

    Returns list of saved file paths. Skips extraction entirely when test_mode_score is True.
    If test_mode_extract is True, still performs extraction (unless test_mode_score) so caller
    can inspect JSON; early return shape preserved if caller set test_mode_extract.
    """
    saved_files: list[str] = []
    if test_mode_score:
        return saved_files

    for raw_link in links:
        try:
            parts = [p for p in raw_link.rstrip("/").split("/") if p]
            candidate_id = parts[-1] if parts else "unknown"
            encoded = requests.utils.quote(raw_link, safe="")
            resp = requests.get(f"{extraction_base}?url={encoded}", timeout=60)
            resp.raise_for_status()
            payload = resp.json()
            if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
                payload = payload["result"]
            out_path = out_dir / f"{candidate_id}.json"
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            saved_files.append(str(out_path))
        except Exception as e:
            print(f"Error extracting {raw_link}: {e}")

    if not test_mode_extract:
        print(f"linkedin_search_tool: extracted {len(saved_files)} profiles to {out_dir}")
    return saved_files


def _prepare_job_description(repo_root: Path) -> tuple[str | None, Path | None]:
    """Return job description text and original file path (if any).

    Ensures a stable filename 'job_description.txt'. Returns (text, original_file) or (None, None)
    if not found or cannot be read.
    """
    jd_dir = repo_root / "ollama_recruiter" / "data" / "jd_input"
    if not jd_dir.exists():
        print("Job description directory not found.")
        return None, None
    txts = sorted(jd_dir.glob("*.txt"))
    if not txts:
        print("Job description file not found.")
        return None, None
    job_file_path = txts[0]
    target = jd_dir / "job_description.txt"
    try:
        if not target.exists():
            shutil.copy(job_file_path, target)
    except Exception:
        pass  # Non-fatal
    try:
        with target.open("r", encoding="utf-8") as f:
            job_text = f.read()
        print("Job description file found.")
        print("Job description content:")
        print(job_text)
        return job_text, job_file_path
    except Exception as e:
        print(f"Error reading job description file: {e}")
        return None, None


def _score_candidates(requests, scorer_url: str, out_dir: Path, job_text: str) -> dict[str, float] | None:
    """Load extracted profiles into scoring service and request scores.

    Returns mapping of candidate_id/link to float score or None if scoring failed.
    """
    try:
        health = requests.get(f"{scorer_url}/health", timeout=10)
        if health.status_code != 200:
            print(f"Scoring API health check failed: status {health.status_code}")
            return None
        print("Scoring API is healthy.")
    except Exception as e:
        print(f"Error checking scoring API health: {e}")
        return None

    try:
        load_payload = {"json_folder": str(out_dir), "exp_agg": "sum_norm", "reset": True}
        load_resp = requests.post(f"{scorer_url}/load_profiles", json=load_payload, timeout=120)
        if load_resp.status_code == 200:
            load_data = load_resp.json()
            print(f"Loaded profiles: {load_data.get('indexed_profiles', 0)} from {load_data.get('source', '')}")
        else:
            print(f"Failed to load profiles: {load_resp.status_code} {load_resp.text}")
            return None
    except Exception as e:
        print(f"Exception loading profiles: {e}")
        return None

    try:
        score_payload = {
            "job_text": job_text,
            "weights": {"experience": 0.4, "skills": 0.4, "education": 0.3, "languages": 0.0},
            "top_k_search": 200,
        }
        score_resp = requests.post(f"{scorer_url}/score", json=score_payload, timeout=180)
        if score_resp.status_code != 200:
            print(f"Failed to score profiles: {score_resp.status_code} {score_resp.text}")
            return None
        score_data = score_resp.json()
        candidates = score_data.get("results") or score_data.get("items") or []
        print("Scoring results (top candidates):")
        results: dict[str, float] = {}
        for item in candidates:
            link = item.get("candidate_id") or item.get("profile_link") or "N/A"
            score = item.get("score") or item.get("total_score")
            results[link] = score
        for link, sc in list(results.items())[:5]:
            print(f"- {link}: Score {sc}")
        return results
    except Exception as e:
        print(f"Exception scoring profiles: {e}")
        return None


def _maybe_cleanup(repo_root: Path, job_file_path: Path | None, out_dir: Path):
    """If CLEANUP_AND_ARCHIVE enabled, archive job description and delete temp JSON files."""
    if not CLEANUP_AND_ARCHIVE:
        return
    try:
        # Move job description into history
        if job_file_path and job_file_path.exists():
            import datetime
            hist_dir = repo_root / "ollama_recruiter" / "data" / "jd_history"
            hist_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            hist_file = hist_dir / f"job_description_{timestamp}.txt"
            try:
                shutil.move(str(job_file_path), hist_file)
                print(f"Archived job description to {hist_file}")
            except Exception as e:
                print(f"Could not archive job description: {e}")
        # Delete temp JSONs
        try:
            deleted = 0
            for f in out_dir.glob("*.json"):
                f.unlink()
                deleted += 1
            print(f"Deleted {deleted} temporary candidate JSON files.")
        except Exception as e:
            print(f"Error deleting temporary JSON files: {e}")
    except Exception as e:  # pragma: no cover - defensive
        print(f"Cleanup encountered an unexpected error: {e}")


def linkedin_search_tool(
    query: str,
    num_candidates: int = 5,
    test_mode_extract: bool = False,
    test_mode_score: bool = False,
) -> dict | list[str]:
    """High-level orchestrator for candidate search + extraction + (optional) scoring.

    Parameters:
        query: search query text
        num_candidates: number of candidates to request from search API
        test_mode_extract: if True, skip remote search and return fixed link list
        test_mode_score: if True, skip extraction & scoring (only gather links)

    Returns:
        If scoring succeeded: dict mapping candidate link/id to score.
        Otherwise: list of candidate links (search output).

    NOTE: Return type retained for backward compatibility. For richer structured
    output a future refactor could introduce a dedicated result object.
    """
    import os  # local to keep surface minimal

    requests = _import_requests()
    if requests is None:
        return FALLBACK_LINKS

    repo_root = _repo_root()
    out_dir = repo_root / "Full system" / "tmp_candids_jsons"
    out_dir.mkdir(parents=True, exist_ok=True)

    search_url = os.getenv("LINKEDIN_SEARCH_URL", "http://127.0.0.1:8000/search")
    extract_url = os.getenv("LINKEDIN_EXTRACT_URL", "http://127.0.0.1:8000/extract")
    scorer_url = os.getenv("CANDIDATE_SCORER_URL", "http://localhost:8001/scorer_tool")

    # 1. Search
    links = _search_candidates(requests, search_url, query, num_candidates, test_mode_extract)

    # 2. Extraction (unless user only wants scoring skipped)
    saved_files = _extract_and_save_profiles(requests, links, extract_url, out_dir, test_mode_score, test_mode_extract)
    if test_mode_extract and not test_mode_score:
        # In original behavior this path returned saved file paths when test_mode_extract true
        return saved_files

    # 3. Job description
    job_text, job_file_path = _prepare_job_description(repo_root)
    if not job_text or test_mode_score:
        return links

    # 4. Scoring
    scores = _score_candidates(requests, scorer_url, out_dir, job_text)
    if scores is None:
        return links

    # 5. Optional cleanup & archiving under global flag
    _maybe_cleanup(repo_root, job_file_path, out_dir)

    return scores


# create a temp test runner
if __name__ == "__main__":
    result = linkedin_search_tool("python backend", 3, test_mode_extract=False, test_mode_score=False)
    print("Returned:", result)