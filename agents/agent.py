"""Main Agent module

Provides a lightweight Agent class that wires together the tools in
`agents.tools`. Includes helpers to build Ollama-style function schemas from
Python callables so the Agent can expose its tools to an LLM (e.g., Ollama).

This file is intentionally dependency-light and serves as an integration
point you can import into the notebook or other scripts.
"""
from typing import List, Dict, get_origin, get_args
import inspect
import os
import sys

# Make imports robust whether this module is run as a script (python agents/agent.py)
# or imported as a package (python -m agents.agent or from agents import Agent).
try:
    from agents.tools import (
        Candidate,
        linkedin_scraper,
        candidates_crawler,
        candidates_embedder,
        interview_question_generator,
    )
except ModuleNotFoundError:
    # If running the file directly, the working directory may be the agents/
    # folder, so ensure the repository root is on sys.path and retry.
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from agents.tools import (
        Candidate,
        linkedin_scraper,
        candidates_crawler,
        candidates_embedder,
        interview_question_generator,
    )


def _map_python_type(py_type):
    """Map simple python/typing types to JSON Schema types used by Ollama."""
    origin = get_origin(py_type)
    args = get_args(py_type)
    # simple builtin types
    if py_type is str:
        return {"type": "string"}
    if py_type is int:
        return {"type": "integer"}
    if py_type is float:
        return {"type": "number"}
    if py_type is bool:
        return {"type": "boolean"}
    # list[...] -> array with items
    if origin in (list, List):
        item_type = args[0] if args else str
        return {"type": "array", "items": _map_python_type(item_type)}
    # dict[...] -> object (loose)
    if origin is dict:
        return {"type": "object"}
    # fallback
    return {"type": "string"}


def func_to_ollama_schema(func, name=None, description=None):
    """Build a minimal Ollama-compatible function schema from a Python function.

    Returns a dict shaped like: {"function": {"name": ..., "description": ..., "parameters": {...}}}
    """
    sig = inspect.signature(func)
    params = {}
    required = []
    for pname, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            # skip *args/**kwargs
            continue
        ann = param.annotation if param.annotation is not inspect._empty else str
        prop_schema = _map_python_type(ann)
        prop_schema["description"] = None
        params[pname] = prop_schema
        if param.default is inspect._empty:
            required.append(pname)

    parameters = {"type": "object", "properties": params}
    if required:
        parameters["required"] = required

    return {
        "function": {
            "name": name or func.__name__,
            "description": description if description is not None else (func.__doc__ or None),
            "parameters": parameters,
        }
    }


def final_answer(answer: str, phone_number: str = "", address: str = "") -> Dict:
    """Simple final answer tool used by the agent / LLM.

    This mirrors the notebook's `final_answer` helper so it can be included in
    the tool schema set returned by `Agent.get_tools_schema()`.
    """
    return {"answer": answer, "phone_number": phone_number, "address": address}


class Agent:
    """Agent wrapper that exposes tools and simple orchestration methods.

    Usage:
        agent = Agent()
        candidates = agent.find_candidates("software engineer ml", max_results=3)
        agent.embed_candidates(candidates)
        questions = agent.make_interview_questions(candidates[0], "Backend Python/ML")
    """

    def __init__(self):
        self.vector_store = []  # simple in-memory store for embeddings (placeholder)

    def find_candidates(self, query: str, max_results: int = 5) -> List[Candidate]:
        """Find and (optionally) enrich candidates.

        Calls `linkedin_scraper` and then `candidates_crawler` to enrich results.
        """
        found = linkedin_scraper(query, max_results=max_results)
        enriched = candidates_crawler(found)
        return enriched

    def embed_candidates(self, candidates: List[Candidate], model: str = "local") -> List[Dict]:
        """Generate embeddings for the given candidates and persist to in-memory store.

        Returns the list of embedding records.
        """
        embeds = candidates_embedder(candidates, model=model)
        # persist to simple in-memory vector_store
        self.vector_store.extend(embeds)
        return embeds

    def make_interview_questions(self, candidate: Candidate, role_description: str) -> List[str]:
        """Generate interview questions for a candidate given a role description."""
        return interview_question_generator(candidate, role_description)

    def get_tools_schema(self) -> List[Dict]:
        """Return Ollama-compatible schemas for the agent's tools.

        This returns schemas for: linkedin_scraper, candidates_crawler,
        candidates_embedder, interview_question_generator, and final_answer.
        """
        tools = [
            func_to_ollama_schema(linkedin_scraper, description="Search LinkedIn for candidates"),
            func_to_ollama_schema(candidates_crawler, description="Enrich candidate records by crawling profile pages"),
            func_to_ollama_schema(candidates_embedder, description="Create embeddings for candidates"),
            func_to_ollama_schema(interview_question_generator, description="Generate interview questions for a candidate"),
            func_to_ollama_schema(final_answer, description="Format and return the final answer"),
        ]
        return tools

    def run_demo(self):
        """Small demo that shows a basic flow using the tools."""
        print("Running agent demo: finding candidates for 'software engineer ml'...")
        candidates = self.find_candidates("software engineer ml", max_results=3)
        print(f"Found {len(candidates)} candidates")
        for c in candidates:
            print(f"- {c.name} | {c.title}")
        embeds = self.embed_candidates(candidates)
        print(f"Created {len(embeds)} embeddings (stored in memory)")
        if candidates:
            q = self.make_interview_questions(candidates[0], "Backend Python/ML role")
            print("Sample interview questions:")
            for qi in q:
                print(f" - {qi}")


if __name__ == "__main__":
    a = Agent()
    a.run_demo()
