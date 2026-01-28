# supabase_client.py
from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple
import os

try:
    import requests
except Exception:
    requests = None

def _get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    # Streamlit secrets first, then env
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets.get(key))
    except Exception:
        pass
    return os.environ.get(key, default)

def _headers(api_key: str) -> Dict[str, str]:
    return {
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": "return=minimal",
    }

def supabase_insert(table: str, row: Dict[str, Any], use_service_role: bool = False) -> Tuple[bool, str]:
    """
    Insert one row into Supabase via REST.
    Needs SUPABASE_URL + SUPABASE_ANON_KEY (or SERVICE key if use_service_role=True).
    Returns (ok, message)
    """
    if not requests:
        return False, "requests nincs telepítve"
    url = _get_secret("SUPABASE_URL")
    anon_key = _get_secret("SUPABASE_ANON_KEY")
    service_key = _get_secret("SUPABASE_SERVICE_KEY")
    api_key = service_key if use_service_role else anon_key
    if not url or not api_key:
        return False, "Hiányzó SUPABASE_URL vagy SUPABASE_ANON_KEY (vagy SERVICE_KEY)"
    endpoint = url.rstrip("/") + f"/rest/v1/{table}"
    try:
        r = requests.post(endpoint, headers=_headers(api_key), data=json_dumps([row]), timeout=10)
        if 200 <= r.status_code < 300:
            return True, "OK"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, "Hálózati hiba"

def supabase_select(table: str, select: str, filters: Optional[List[str]] = None, limit: int = 5000) -> Tuple[bool, Any]:
    """
    Select rows via REST using SERVICE key (recommended) or ANON if allowed.
    Filters are raw query strings like 'ym=eq.2026-01' or 'zip=is.null' etc.
    """
    if not requests:
        return False, "requests nincs telepítve"
    url = _get_secret("SUPABASE_URL")
    service_key = _get_secret("SUPABASE_SERVICE_KEY")
    anon_key = _get_secret("SUPABASE_ANON_KEY")
    api_key = service_key or anon_key
    if not url or not api_key:
        return False, "Hiányzó SUPABASE_URL és kulcs"
    q = f"select={select}&limit={limit}"
    if filters:
        for f in filters:
            q += "&" + f
    endpoint = url.rstrip("/") + f"/rest/v1/{table}?{q}"
    try:
        r = requests.get(endpoint, headers=_headers(api_key), timeout=15)
        if 200 <= r.status_code < 300:
            return True, r.json()
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except Exception:
        return False, "Hálózati hiba"

def json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
