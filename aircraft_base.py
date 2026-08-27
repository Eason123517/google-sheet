from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class AircraftProfile:
    code: str
    display_name: str
    aircraft_type: str
    status_text: str
    description: str
    allow_packing: bool
    module_file: str
    notes: tuple[str, ...] = ()
