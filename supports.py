# supports.py
from __future__ import annotations
from typing import Dict, Any, List

def match_supports(inputs: Dict[str, Any], results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """V18: teljes lista, egyszerű relevancia pontozás (v1)."""
    base = results.get("supports", [])
    scored = []
    for s in base:
        score = 3
        focus = (s.get("focus") or "").lower()
        if "padlás" in focus or "szigetelés" in focus:
            score += 1
        if results.get("energy_class_light") in ["F", "G"]:
            score += 1
        scored.append({**s, "score": min(5, score)})
    return scored
