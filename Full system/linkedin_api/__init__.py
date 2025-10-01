"""linkedin_api package initializer.

This file makes `linkedin_api` a Python package so relative imports in
`server.py` work when started with uvicorn from the project root.
"""

__all__ = [
    "server",
]
