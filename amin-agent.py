"""Thin launcher for the refactored amin_agent package.

This file intentionally kept as small entrypoint that calls
the package-level build_and_run() function implemented in
the `amin_agent` package.
"""

from amin_agent.main import build_and_run


if __name__ == "__main__":
    build_and_run()