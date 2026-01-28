# calculator.py
# V20 – Lakosságbarát, kombinált energetikai számítási motor (becslés)
# A számítások nem hivatalos energetikai tanúsítványt adnak, hanem döntéstámogató becslést.

from __future__ import annotations
from typing import Dict, Any, Tuple

# --- CO2 faktorok (becslés) ---
ELECTRIC_CO2 = 0.21  # kg CO2 / kWh (HU átlag becslés)
GAS_CO2 = 0.20       # kg CO2 / kWh (földgáz égésből)

# --- Magyar rezsi sávok (felhasználó által megadott értékek alapján) ---
ELECTRIC_PRICE_LOW = 36.386   # Ft/kWh
ELECTRIC_PRICE_HIGH = 70.104  # Ft/kWh
ELECTRIC_LIMIT_KWH = 2523     # kWh/év

GAS_PRICE_LOW = 102.0     # Ft/m3
GAS_PRICE_HIGH = 747.0    # Ft/m3
GAS_LIMIT_M3 = 1729.0     # m3/év
GAS_KWH_PER_M3 = 9.44     # kWh/m3 (tipikus)

# --- Tipikus fajlagos fűtési energiaigény sávok (kWh/m2/év) ---
HEATING_INTENSITY = {"jó": 90.0, "közepes": 140.0, "rossz": 200.0}

# --- Tipikus HMV igény (kWh/fő/év) ---
DHW_KWH_PER_PERSON = 800.0

# --- Tipikus villany alap (kWh/fő/év) ---
ELEC_KWH_PER_PERSON = 650.0


def split_by_tier_from_energy(total_kwh: float, limit_kwh: float, low_price: float, high_price: float) -> Tuple[float, float, float]:
    low_kwh = min(total_kwh, limit_kwh)
    high_kwh = max(0.0, total_kwh - limit_kwh)
    cost = low_kwh * low_price + high_kwh * high_price
    return low_kwh, high_kwh, cost


def energy_from_cost_with_tier(total_cost_huf: float, limit_kwh: float, low_price: float, high_price: float) -> float:
    if total_cost_huf <= 0:
        return 0.0
    cost_at_limit = limit_kwh * low_price
    if total_cost_huf <= cost_at_limit:
        return total_cost_huf / low_price
    remaining = total_cost_huf - cost_at_limit
    return limit_kwh + remaining / high_price


def gas_kwh_from_m3(m3: float) -> float:
    return max(0.0, m3) * GAS_KWH_PER_M3


def gas_m3_from_cost(total_cost_huf: float) -> float:
    if total_cost_huf <= 0:
        return 0.0
    cost_at_limit = GAS_LIMIT_M3 * GAS_PRICE_LOW
    if total_cost_huf <= cost_at_limit:
        return total_cost_huf / GAS_PRICE_LOW
    remaining = total_cost_huf - cost_at_limit
    return GAS_LIMIT_M3 + remaining / GAS_PRICE_HIGH


def estimate_building_quality(wall_q: str, attic_q: str, window_q: str) -> str:
    score = 0
    for q in (wall_q, attic_q, window_q):
        if q == "jó":
            score += 0
        elif q == "közepes":
            score += 1
        else:
            score += 2
    if score <= 1:
        return "jó"
    if score <= 3:
        return "közepes"
    return "rossz"


def energy_class_light(total_kwh_per_m2: float) -> str:
    if total_kwh_per_m2 < 70:
        return "B"
    if total_kwh_per_m2 < 110:
        return "C"
    if total_kwh_per_m2 < 150:
        return "D"
    if total_kwh_per_m2 < 190:
        return "E"
    if total_kwh_per_m2 < 240:
        return "F"
    return "G"


def _norm_quality(x: str) -> str:
    if x in ("jó (2010 után)", "jó", "Jó"):
        return "jó"
    if x in ("közepes (1990–2010)", "közepes", "Közepes"):
        return "közepes"
    return "rossz"


def calculate(inputs: Dict[str, Any]) -> Dict[str, Any]:
    area_m2 = float(inputs.get("area_m2") or 0) or 0.0
    people = int(inputs.get("people") or 0) or 0
    if area_m2 <= 0:
        area_m2 = 80.0  # fallback

    wall_q = _norm_quality(inputs.get("wall_quality", "Nem tudom"))
    attic_q = _norm_quality(inputs.get("attic_quality", "Nem tudom"))
    win_q = _norm_quality(inputs.get("window_quality", "Nem tudom"))
    building_q = estimate_building_quality(wall_q, attic_q, win_q)

    annual_elec_cost = float(inputs.get("annual_electric_cost") or 0) or 0.0
    standby_w = float(inputs.get("standby_w") or 0) or 0.0
    fridges = int(inputs.get("fridge_count") or 0) or 0

    if annual_elec_cost > 0:
        annual_elec_kwh = energy_from_cost_with_tier(
            annual_elec_cost, ELECTRIC_LIMIT_KWH, ELECTRIC_PRICE_LOW, ELECTRIC_PRICE_HIGH
        )
        elec_source = "villany Ft"
    else:
        fridge_kwh = fridges * 350.0
        standby_kwh = standby_w * 24 * 365 / 1000.0
        annual_elec_kwh = max(0.0, people * ELEC_KWH_PER_PERSON + fridge_kwh + standby_kwh)
        elec_source = "becslés"

    heating_type = str(inputs.get("heating_type", "Nem tudom"))
    annual_gas_m3 = float(inputs.get("annual_gas_m3") or 0) or 0.0
    annual_gas_cost = float(inputs.get("annual_gas_cost") or 0) or 0.0

    heating_kwh = 0.0
    heating_source = "becslés"
    if heating_type.lower().startswith("gáz") or "kazán" in heating_type.lower() or "konvektor" in heating_type.lower():
        if annual_gas_m3 > 0:
            heating_kwh = gas_kwh_from_m3(annual_gas_m3)
            heating_source = "gáz m³"
        elif annual_gas_cost > 0:
            heating_kwh = gas_kwh_from_m3(gas_m3_from_cost(annual_gas_cost))
            heating_source = "gáz Ft"
        else:
            heating_kwh = area_m2 * HEATING_INTENSITY[building_q]
            heating_source = "fajlagos (m²)"
    elif "klíma" in heating_type.lower() or "hőszivattyú" in heating_type.lower():
        if annual_elec_cost > 0:
            heating_kwh = annual_elec_kwh * 0.55
            heating_source = "villany Ft (arányos)"
        else:
            heating_kwh = area_m2 * HEATING_INTENSITY[building_q] * 0.6
            heating_source = "fajlagos (m², COP)"
    elif "elektromos" in heating_type.lower() or "radiátor" in heating_type.lower() or "nobo" in heating_type.lower():
        if annual_elec_cost > 0:
            heating_kwh = annual_elec_kwh * 0.65
            heating_source = "villany Ft (arányos)"
        else:
            heating_kwh = area_m2 * HEATING_INTENSITY[building_q]
            heating_source = "fajlagos (m²)"
    else:
        heating_kwh = area_m2 * HEATING_INTENSITY[building_q]
        heating_source = "fajlagos (m²)"

    dhw_type = str(inputs.get("dhw_type", "Nem tudom"))
    dhw_kwh = (people if people > 0 else 2) * DHW_KWH_PER_PERSON
    dhw_source = "becslés"

    gas_kwh_total = 0.0
    gas_cost = 0.0
    if annual_gas_m3 > 0:
        low_m3 = min(annual_gas_m3, GAS_LIMIT_M3)
        high_m3 = max(0.0, annual_gas_m3 - GAS_LIMIT_M3)
        gas_cost = low_m3 * GAS_PRICE_LOW + high_m3 * GAS_PRICE_HIGH
        gas_kwh_total = gas_kwh_from_m3(annual_gas_m3)
    elif annual_gas_cost > 0:
        m3 = gas_m3_from_cost(annual_gas_cost)
        low_m3 = min(m3, GAS_LIMIT_M3)
        high_m3 = max(0.0, m3 - GAS_LIMIT_M3)
        gas_cost = low_m3 * GAS_PRICE_LOW + high_m3 * GAS_PRICE_HIGH
        gas_kwh_total = gas_kwh_from_m3(m3)

    if ("gáz" in dhw_type.lower()) and gas_kwh_total > 0:
        dhw_kwh = max(dhw_kwh, gas_kwh_total * 0.15)
        dhw_source = "gáz arány"

    total_kwh = annual_elec_kwh + heating_kwh + dhw_kwh
    kwh_per_m2 = total_kwh / max(1.0, area_m2)
    eclass = energy_class_light(kwh_per_m2)

    elec_low, elec_high, elec_cost = split_by_tier_from_energy(
        annual_elec_kwh, ELECTRIC_LIMIT_KWH, ELECTRIC_PRICE_LOW, ELECTRIC_PRICE_HIGH
    )

    elec_co2 = annual_elec_kwh * ELECTRIC_CO2
    gas_co2 = gas_kwh_total * GAS_CO2
    total_co2 = elec_co2 + gas_co2

    # Simple TOP recs
    recs = []
    if attic_q != "jó":
        save = heating_kwh * 0.18
        recs.append({
            "title": "Padlásfödém szigetelés",
            "why": "Gyors és nagy hatású. EKR-ben néha „ingyenes jellegű” kivitelezés is elérhető.",
            "save_kwh_y": save,
            "save_huf_y": save * (GAS_PRICE_LOW / GAS_KWH_PER_M3) if gas_kwh_total > 0 else save * ELECTRIC_PRICE_LOW,
            "save_co2_kg_y": save * (GAS_CO2 if gas_kwh_total > 0 else ELECTRIC_CO2),
            "payback_y": 3.0
        })
    if wall_q != "jó":
        save = heating_kwh * 0.12
        recs.append({
            "title": "Homlokzati hőszigetelés (15 cm – ár/érték optimum)",
            "why": "15 cm körül gyakran a legjobb ár/érték; 20 cm már kisebb többlet-megtakarítást ad.",
            "save_kwh_y": save,
            "save_huf_y": save * (GAS_PRICE_LOW / GAS_KWH_PER_M3) if gas_kwh_total > 0 else save * ELECTRIC_PRICE_LOW,
            "save_co2_kg_y": save * (GAS_CO2 if gas_kwh_total > 0 else ELECTRIC_CO2),
            "payback_y": 12.0
        })
    if win_q != "jó":
        save = heating_kwh * 0.10
        recs.append({
            "title": "Nyílászáró korszerűsítés",
            "why": "A jó beépítés (hőhidak, redőnytok) legalább annyit számít, mint az üvegréteg.",
            "save_kwh_y": save,
            "save_huf_y": save * (GAS_PRICE_LOW / GAS_KWH_PER_M3) if gas_kwh_total > 0 else save * ELECTRIC_PRICE_LOW,
            "save_co2_kg_y": save * (GAS_CO2 if gas_kwh_total > 0 else ELECTRIC_CO2),
            "payback_y": 14.0
        })

    supports = [
        {"name": "EKR / energiahatékonysági programok", "focus": "padlásfödém, szigetelés", "notes": "Energiamegtakarítás után járó finanszírozás, kivitelezői ajánlatokkal."},
        {"name": "Otthonfelújítási energetikai programok (pl. 3+3 jelleg)", "focus": "szigetelés + nyílászáró + fűtés", "notes": "Komplex felújításnál jellemző. Feltételek programonként eltérnek."},
        {"name": "Otthoni energiatároló (akkumulátor) programok", "focus": "napelem mellé tároló", "notes": "Napelem mellett segít a saját fogyasztás növelésében."},
    ]

    return {
        "meta": {
            "method": "V20-SIMPLE-COMBINED",
            "building_quality": building_q,
            "electricity_source": elec_source,
            "heating_source": heating_source,
            "dhw_source": dhw_source,
        },
        "energy_kwh": {
            "electricity": annual_elec_kwh,
            "heating": heating_kwh,
            "dhw": dhw_kwh,
            "total": total_kwh,
            "per_m2": kwh_per_m2,
        },
        "cost_huf": {
            "electricity_total": elec_cost,
            "gas_total": gas_cost,
            "total": elec_cost + gas_cost,
            "electricity_split": {"low_kwh": elec_low, "high_kwh": elec_high},
        },
        "co2_kg": {"electricity": elec_co2, "gas": gas_co2, "total": total_co2},
        "energy_class_light": eclass,
        "recommendations": recs[:3],
        "supports": supports,
    }
