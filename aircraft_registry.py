from __future__ import annotations

import aircraft_a333
import aircraft_b777


_MODULES = {
    "A333": aircraft_a333,
    "B777": aircraft_b777,
}


def aircraft_codes() -> list[str]:
    return list(_MODULES.keys())


def get_aircraft_module(code: str):
    try:
        return _MODULES[code]
    except KeyError as exc:
        raise KeyError(f"未知機型：{code}") from exc


def get_aircraft_profile(code: str):
    return get_aircraft_module(code).PROFILE


def aircraft_label(code: str) -> str:
    p = get_aircraft_profile(code)
    return f"{p.code}｜{p.display_name}"
