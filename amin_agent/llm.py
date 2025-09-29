"""LLM utilities: Ollama wrapper and schema builder helpers.

This module preserves the minimal behaviour of the original script so the
package runs without external dependencies.
"""

import inspect
import typing
import json
from typing import get_origin, get_args

try:
    import ollama
except Exception:
    # Local stub for testing
    class _OllamaStub:
        @staticmethod
        def chat(model: str, messages: list, format: str = "json"):
            # deterministic example response instructing to call linkedin_scraper
            payload = {
                "name": "linkedin_scraper",
                "parameters": {"query": "software engineer ml", "max_results": 2}
            }
            return {"message": {"content": json.dumps(payload)}}

    ollama = _OllamaStub()


def _map_python_type(py_type):
    origin = get_origin(py_type)
    args = get_args(py_type)
    if py_type is str:
        return {"type": "string"}
    if py_type is int:
        return {"type": "integer"}
    if py_type is float:
        return {"type": "number"}
    if py_type is bool:
        return {"type": "boolean"}
    if origin in (list, typing.List):
        item_type = args[0] if args else str
        return {"type": "array", "items": _map_python_type(item_type)}
    if origin in (dict, typing.Dict):
        return {"type": "object"}
    return {"type": "string"}


def func_to_ollama_schema(func, name=None, description=None):
    """Build a minimal Ollama function schema from a Python function.

    The returned dict has the shape used by the original script and is
    intentionally small.
    """
    sig = inspect.signature(func)
    params = {}
    required = []
    for pname, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
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


def call_ollama(model: str, messages: list):
    """Call the ollama.chat function and return its raw response.

    Kept as a thin wrapper so unit tests can patch it if needed.
    """
    return ollama.chat(model=model, messages=messages, format="json")
