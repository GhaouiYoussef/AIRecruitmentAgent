# Agent architecture for Candidate Search & Interview Assistant

This document describes the proposed agent architecture and where tools such as
the LinkedIn scraper, candidates embedder, candidates crawler, and interview
question generator fit into the system. Use this as a guide and a landing page
for the small `agents` Python package in this repository.

## High-level components

- Oracle (LLM)
  - Responsible for deciding what to do next, orchestrating tool calls, and
    producing final natural-language outputs. In the notebook this is the
    `oracle` / `call_llm` component.

- Tools (external functions)
  - Independent, testable functions that perform discrete tasks. Examples:
    - `linkedin_scraper` — find candidate profiles.
    - `candidates_crawler` — crawl additional pages or profile sources.
    - `candidates_embedder` — convert candidate data into vector embeddings.
    - `interview_question_generator` — generate interview questions for a
      specific candidate or role.

- Agent State / Graph
  - Maintains conversation state, intermediate tool outputs, and the final
    answer. Implemented in the notebook using LangGraph's `StateGraph`.

- Vector store / persistence (optional)
  - Stores candidate embeddings for retrieval. Could be Pinecone, FAISS,
    Milvus, or a simple on-disk store for experiments.

## How the pieces interact (flow)

1. User provides intent (e.g., "Find a software engineer with ML experience").
2. Oracle decides which tool to call (e.g., `linkedin_scraper`).
3. `linkedin_scraper` returns structured candidate records.
4. Optionally: `candidates_crawler` expands the set by following links.
5. `candidates_embedder` creates embeddings for the candidates and stores
   them in a vector DB.
6. Oracle calls `interview_question_generator` to make tailored questions for
   shortlisted candidates.
7. Oracle calls `final_answer` tool to format the final response.

## Where to add your own tools

- Implement tools as simple Python functions that accept primitive types or
  Pydantic models and return serializable objects (dicts, lists, strings). This
  simplifies converting them to Ollama function schemas or other tool-schema
  formats.

- The `agents/tools.py` module contains starting placeholders you can wire into
  the notebook's LangGraph nodes and Ollama function schemas.

## Next improvements

- Add a proper embedding backend (requirements and wiring).
- Replace placeholders with real scrapers or API-based connectors.
- Add unit tests and a small CLI to exercise each tool independently.

## Files

- `agents/tools.py` — placeholders for the core tools.
