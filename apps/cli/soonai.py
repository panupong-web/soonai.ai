"""Canonical CLI entrypoint for the SoonAI application layout.

The root ``soonai.py`` remains as a compatibility launcher for existing
installations and scripts. Keeping the delegation here makes the new
application/package boundary explicit without changing runtime behavior.
"""

from __future__ import annotations

import runpy
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LEGACY_ENTRYPOINT = REPOSITORY_ROOT / "soonai.py"


def main() -> None:
    """Run the compatibility entrypoint with the original CLI arguments."""
    runpy.run_path(str(LEGACY_ENTRYPOINT), run_name="__main__")


if __name__ == "__main__":
    main()
