"""Developer CLI entry point.

The contract CLI is intentionally completed after the room-safe P1 actions are
implemented.  It must never provide a bypass for human approvals or publishing.
"""

from __future__ import annotations


def main() -> int:
    """Run the Carbon Room developer CLI (implemented in P1-1.6)."""
    raise NotImplementedError("owner: P1, story P1-1.6")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
