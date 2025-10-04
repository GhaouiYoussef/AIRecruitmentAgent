import json 
from pathlib import Path
import shutil


def linkedin_search_tool(query: str, num_candidates: int = 5, test_mode_extract: bool = False, test_mode_score: bool = False) -> dict | list[str]:
    import os
    try:
        import requests
    except Exception as e:
        print(f"linkedin_search_tool: requests not available: {e}; returning fallback links")
        return [
            "https://www.linkedin.com/in/saber-chadded-36552b192/",
            "https://www.linkedin.com/in/guesmi-wejden-5269222aa/",
            "https://www.linkedin.com/in/hichem-dridi/",
            "https://www.linkedin.com/in/nour-hamdi/",
            "https://www.linkedin.com/in/iyadh-chaouch-072077225/",
        ]

    service_url = os.getenv("LINKEDIN_SEARCH_URL", "http://127.0.0.1:8000/search")
    try:
        if not test_mode_extract:
            # Call the search service
            resp = requests.get(service_url, params={"query": query, "num_candidates": int(num_candidates)}, timeout=500)
            resp.raise_for_status()
            data = resp.json()
            links = None
            if isinstance(data, dict):
                links = data.get("links") or data.get("results") or data.get("candidates")
            if not links or not isinstance(links, list):
                raise ValueError(f"unexpected response shape: {data}")
        else:
            # Test mode: return fixed links
            links = [
                "https://www.linkedin.com/in/saber-chadded-36552b192/",
                "https://www.linkedin.com/in/guesmi-wejden-5269222aa/",
                # "https://www.linkedin.com/in/hichem-dridi/",
                # "https://www.linkedin.com/in/nour-hamdi/",
                # "https://www.linkedin.com/in/iyadh-chaouch-072077225/",
            ]
            
        # preparing for the extraction and saving JSON files api calls
        
        saved_files = []
        # Prepare output directory (repo_root / "Full system" / "tmp_candids_jsons")

        repo_root = Path(__file__).resolve().parent.parent
        out_dir = repo_root / "Full system" / "tmp_candids_jsons"
        out_dir.mkdir(parents=True, exist_ok=True)

        if not test_mode_score :
            extraction_base = os.getenv("LINKEDIN_EXTRACT_URL", "http://127.0.0.1:8000/extract")

            for raw_link in links:
                try:
                    # Extract candidate id BEFORE encoding (handles trailing slash)
                    parts = [p for p in raw_link.rstrip("/").split("/") if p]
                    candidate_id = parts[-1] if parts else "unknown"

                    encoded = requests.utils.quote(raw_link, safe="")
                    resp = requests.get(f"{extraction_base}?url={encoded}", timeout=500)
                    resp.raise_for_status()
                    data = resp.json()

                    # If API wraps result like {"result": {...}}, unwrap
                    if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
                        payload = data["result"]
                    else:
                        payload = data

                    out_path = out_dir / f"{candidate_id}.json"
                    with out_path.open("w", encoding="utf-8") as f:
                        json.dump(payload, f, ensure_ascii=False, indent=2)
                    saved_files.append(str(out_path))
                except Exception as e:
                    print(f"Error extracting {raw_link}: {e}")

            if test_mode_extract:
                return saved_files
            else:
                print(f"linkedin_search_tool: extracted {len(saved_files)} profiles to {out_dir}", flush=True)
            
        # if we are going to score them
        # we check if we have a text file in data/jd_input
        jd_dir = repo_root / "ollama_recruiter" / "data" / "jd_input"
        txts = sorted(jd_dir.glob("*.txt")) if jd_dir.exists() else []
        if txts:
            # ensure a stable filename the rest of the code expects
            job_file_path = txts[0]
            target = jd_dir / "job_description.txt"
            try:
                if not target.exists():
                    shutil.copy(job_file_path, target)
            except Exception:
                # ignore copy errors; we'll still attempt to open the original file below if needed
                pass
            print("Job description file found.")
            try:
                with open(repo_root / "ollama_recruiter" / "data" / "jd_input" / "job_description.txt", "r", encoding="utf-8") as f:
                    job_text = f.read()
                print("Job description content:")
                print(job_text)
                # we call the scoring api
                # we check the status curl --location 'http://localhost:8001/scorer_tool/health'

                scorer_url = os.getenv("CANDIDATE_SCORER_URL", "http://localhost:8001/scorer_tool")
                try:
                    response = requests.get(f"{scorer_url}/health")
                    if response.status_code == 200:
                        print("Scoring API is healthy.")

                     # if healthy we call the load profiles endpoint curl --location 'http://localhost:8001/scorer_tool/load_profiles' \
# --header 'Content-Type: application/json' \
# --data '{
#   "json_folder": "c:\\YoussefENSI_backup\\Eukliadia-test\\json_candids",
#   "exp_agg": "sum_norm",
#   "reset": true
# }'
                        load_payload = {
                            "json_folder": str(out_dir),
                            "exp_agg": "sum_norm",
                            "reset": True
                        }
                        load_response = requests.post(f"{scorer_url}/load_profiles", json=load_payload)
                        if load_response.status_code == 200:
                            load_data = load_response.json()
                            print(f"Loaded profiles: {load_data.get('indexed_profiles', 0)} from {load_data.get('source', '')}")
                        else:
                            print(f"Failed to load profiles, status code: {load_response.status_code}, detail: {load_response.text}")

                        # now we call the scoring endpoint curl --location 'http://localhost:8001/scorer_tool/score' \
#                         curl --location 'http://localhost:8001/scorer_tool/score' \
# --header 'Content-Type: application/json' \
# --data '{
#   "job_text": "We need a Python ML engineer with NLP experience, transformers, and FastAPI. English required.",
#   "weights": {
#     "experience": 0.4,
#     "skills": 0.4,
#     "education": 0.3,
#     "languages": 0.0
#   },
#   "top_k_search": 200
# }
# '
                        score_payload = {
                            "job_text": job_text,
                            "weights": {
                                "experience": 0.4,
                                "skills": 0.4,
                                "education": 0.3,
                                "languages": 0.0
                            },
                            "top_k_search": 200
                        }
                        score_response = requests.post(f"{scorer_url}/score", json=score_payload)
                        if score_response.status_code == 200:
                            score_data = score_response.json()
                            # New response format example:
                            # {
                            #   "count": 2,
                            #   "results": [
                            #       {"candidate_id": "<url>", "score": 0.47, "breakdown": {...}}, ...
                            #   ]
                            # }
                            # Old (fallback) format expected earlier:
                            # {"items": [{"profile_link": "<url>", "total_score": 0.47}, ...]}
                            candidates = (
                                score_data.get("results")
                                or score_data.get("items")
                                or []
                            )
                            print("Scoring results (top candidates):")
                            def _extract(item: dict):
                                link = (
                                    item.get("candidate_id")
                                    or "N/A"
                                )
                                sc = item.get("score")
                                return link, sc
                            for item in candidates[:5]:  # print top 5
                                link, sc = _extract(item)
                                print(f"- {link}: Score {sc}")

                            
                            # move the description file to data/jd_history with a timestamp
                            # import datetime
                            # timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            # hist_dir = repo_root / "ollama_recruiter" / "data" / "jd_history"
                            # hist_dir.mkdir(parents=True, exist_ok=True)
                            # hist_file = hist_dir / f"job_description_{timestamp}.txt"
                            # try:
                            #     shutil.move(job_file_path, hist_file)
                            # except Exception:
                            #     # ignore copy errors; we'll still attempt to open the original file below if needed
                            #     pass

                            # delete the files in tmp_candids_jsons
                            # try:
                            #     for f in out_dir.glob("*.json"):
                            #         f.unlink()
                            # except Exception as e:
                            #     print(f"Error deleting temporary JSON files: {e}")
                                
                            # we return a dict of all the candidates ordered by score,
                            # Return a dict mapping candidate link to score using unified extraction
                            return { _extract(item)[0]: _extract(item)[1] for item in candidates }
                        else:
                            print(f"Failed to score profiles, status code: {score_response.status_code}, detail: {score_response.text}")


                     #    
                    else:
                        print(f"Scoring API returned status code {response.status_code}.")
                except Exception as e:
                    print(f"Error checking scoring API health: {e}")

            except Exception as e:
                print(f"Error reading job description file: {e}")
        else:
            print("Job description file not found.")
            return links

    except Exception as e:
        print(f"linkedin_search_tool: remote call failed ({e}); returning fallback links")
        return links

# create a temp test runner
if __name__ == "__main__":
    files = linkedin_search_tool("python backend", 3, test_mode_extract=False, test_mode_score=False)
    print("Returned:", files)