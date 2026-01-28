# banding.py
from __future__ import annotations
from typing import Optional

def area_band(area_m2: float) -> str:
    if area_m2 < 50:
        return "<50"
    if area_m2 < 80:
        return "50-80"
    if area_m2 < 120:
        return "80-120"
    if area_m2 < 160:
        return "120-160"
    return "160+"

def cost_band(huf: float) -> str:
    if huf < 100_000:
        return "<100k"
    if huf < 200_000:
        return "100-200k"
    if huf < 400_000:
        return "200-400k"
    return "400k+"

def kwh_m2_band(kwh_m2: float) -> str:
    if kwh_m2 < 110:
        return "alacsony"
    if kwh_m2 < 190:
        return "kozepes"
    return "magas"

def co2_band(co2_kg: float) -> str:
    if co2_kg < 2000:
        return "alacsony"
    if co2_kg < 5000:
        return "kozepes"
    return "magas"

def build_era(value: Optional[str]) -> str:
    if not value:
        return "ismeretlen"
    v = str(value).lower()
    # accept both years and ranges
    # If it's a year like "1975"
    try:
        y = int("".join(ch for ch in v if ch.isdigit())[:4])
        if y < 1960:
            return "1960_elott"
        if y < 1980:
            return "1960_1980"
        if y < 2000:
            return "1980_2000"
        return "2000_utan"
    except Exception:
        pass
    if "1960" in v or "50" in v or "kor" in v:
        return "1960_elott"
    if "60" in v or "70" in v:
        return "1960_1980"
    if "80" in v or "90" in v:
        return "1980_2000"
    if "2000" in v or "2010" in v or "2020" in v:
        return "2000_utan"
    return "ismeretlen"
