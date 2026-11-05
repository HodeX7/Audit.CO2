"""Carbon Room's contract-compatible public package.

The existing :mod:`carbonroom` package remains available while teammates migrate to
the frozen ``carbon_room`` contract.
"""

from carbon_room.models import CarbonRoomError

__all__ = ["CarbonRoomError"]
