
def linkedin_search_tool(query: str, num_candidates: int = 5):
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
        resp = requests.get(service_url, params={"query": query, "num_candidates": int(num_candidates)}, timeout=500)
        resp.raise_for_status()
        data = resp.json()
        links = None
        if isinstance(data, dict):
            links = data.get("links") or data.get("results") or data.get("candidates")
        if not links or not isinstance(links, list):
            raise ValueError(f"unexpected response shape: {data}")
        # if TOP_K != None:
        return links
    except Exception as e:
        print(f"linkedin_search_tool: remote call failed ({e}); returning fallback links")
        return [
            "https://www.linkedin.com/in/saber-chadded-36552b192/",
            "https://www.linkedin.com/in/guesmi-wejden-5269222aa/",
            "https://www.linkedin.com/in/hichem-dridi/",
            "https://www.linkedin.com/in/nour-hamdi/",
            "https://www.linkedin.com/in/iyadh-chaouch-072077225/",
        ]
