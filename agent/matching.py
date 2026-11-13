"""Who to ask first: cleaners sorted by public-transport time to the shift.

No cut-off here: workflow takes the nearest 2N and applies each cleaner's own
learned limit (max_travel_minutes) and rules.
"""
from shared.schemas import Cleaner, Shift


def shortlist(shift: Shift, cleaners: list[Cleaner], minutes: dict[str, int]) -> list[Cleaner]:
    """Cleaners with a known travel time, nearest first."""
    return sorted((c for c in cleaners if c.id in minutes), key=lambda c: minutes[c.id])
