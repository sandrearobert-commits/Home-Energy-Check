# recommendations.py
from __future__ import annotations
from typing import Dict, Any, List

def top_recommendations(results: Dict[str, Any]) -> List[Dict[str, Any]]:
    return results.get("recommendations", [])
