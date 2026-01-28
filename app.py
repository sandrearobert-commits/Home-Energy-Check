# Energia & CO₂ Audit – V15 (deploy-stabilizálás + theme/runtime pin + további mezők/javaslatok)
# Futás: streamlit run app.py
# Secrets (Streamlit Cloud):
#   ADMIN_PASSWORD="..."
#   DATABASE_URL=""   # opcionális (ha üres, lokális SQLite)

import os
import io
import sqlite3
import datetime as dt
from typing import Optional, Tuple, List, Dict

import pandas as pd
import numpy as np
import streamlit as st

import json
import time
try:
    import requests
except Exception:
    requests = None


from calculator import calculate
from pdf_report import build_pdf_report
from supports import match_supports
from recommendations import top_recommendations
from supabase_client import supabase_insert, supabase_select
from banding import area_band, cost_band, kwh_m2_band, co2_band, build_era


# --- V16 helpers: fast startup + cached data loading
@st.cache_data(show_spinner=False)
def load_csv_cached(path: str):
    import pandas as pd
    return pd.read_csv(path)

@st.cache_data(show_spinner=False)
def load_yaml_cached(path: str):
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
# (V16) reportlab imported lazily inside PDF exporter
# (V16) reportlab imported lazily inside PDF exporter
# (V16) reportlab imported lazily inside PDF exporter

st.set_page_config(page_title="Energia & CO₂ Audit", page_icon="🏠", layout="wide")
# ---------------- UI (pro look) ----------------
st.markdown(
    """<style>
    :root{
      --bg:#0b1220;
      --card:#0f1a2b;
      --card2:#0c1727;
      --text:#e8eefc;
      --muted:#a9b4d0;
      --border:rgba(255,255,255,.10);
      --accent:#6ea8fe;
      --good:#2ecc71;
      --warn:#f1c40f;
      --bad:#ff5c5c;
    }
    /* page */
    .stApp { background: linear-gradient(180deg, #070b14 0%, #0b1220 40%, #070b14 100%); color: var(--text); }
    /* widen + tidy */
    [data-testid="stVerticalBlockBorderWrapper"]{ background: transparent; border: 0; }
    /* cards */
    .hec-card{
      background: radial-gradient(1200px 600px at 20% 0%, rgba(110,168,254,.18), transparent 60%),
                  linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.03));
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 14px 14px;
      box-shadow: 0 10px 30px rgba(0,0,0,.35);
    }
    .hec-title{
      display:flex; align-items:center; gap:10px;
      font-weight:700; font-size: 18px; margin: 0 0 10px 0;
    }
    .hec-title svg{ width:22px; height:22px; opacity:.95; }
    .hec-badge{
      margin-left:auto;
      font-size:12px;
      color: var(--text);
      background: rgba(110,168,254,.15);
      border:1px solid rgba(110,168,254,.35);
      padding: 4px 10px;
      border-radius: 999px;
      white-space:nowrap;
    }
    .hec-subtle{ color: var(--muted); font-size: 12px; margin-top: -6px; }
    /* inputs */
    .stSelectbox, .stTextInput, .stNumberInput, .stRadio, .stSlider { color: var(--text); }
    /* hide default header space a bit */
    header{ background: transparent !important; }
    </style>""",
    unsafe_allow_html=True
)

def _svg(name: str) -> str:
    # Minimal inline SVG set (no external icon packs, works offline)
    icons = {
        "pin": """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 22s7-4.5 7-12a7 7 0 10-14 0c0 7.5 7 12 7 12z" stroke="currentColor" stroke-width="2"/>
          <path d="M12 10.5a2.5 2.5 0 110-5 2.5 2.5 0 010 5z" stroke="currentColor" stroke-width="2"/>
        </svg>""",
        "roadsign": """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M8 4h10l3 4-3 4H8L5 8l3-4z" stroke="currentColor" stroke-width="2" />
          <path d="M12 12v10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>""",
        "home": """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M3 11l9-8 9 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M5 10v10h14V10" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          <path d="M10 20v-6h4v6" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
        </svg>""",
        "flame": """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 22c4 0 7-3 7-7 0-3-2-5-3-6 0 2-1 3-2 4 0-4-2-7-5-9 1 4-3 6-3 11 0 4 3 7 6 7z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
        </svg>""",
        "drop": """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 2s7 7 7 12a7 7 0 11-14 0C5 9 12 2 12 2z" stroke="currentColor" stroke-width="2"/>
        </svg>""",
        "bolt": """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M13 2L3 14h7l-1 8 12-14h-7l-1-6z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
        </svg>""",
        "layers": """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 3l9 5-9 5-9-5 9-5z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          <path d="M3 12l9 5 9-5" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          <path d="M3 17l9 5 9-5" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
        </svg>""",
        "window": """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M4 4h16v16H4V4z" stroke="currentColor" stroke-width="2"/>
          <path d="M12 4v16" stroke="currentColor" stroke-width="2"/>
          <path d="M4 12h16" stroke="currentColor" stroke-width="2"/>
        </svg>""",
        "plug": """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M9 3v6M15 3v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          <path d="M7 9h10v5a5 5 0 01-10 0V9z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
          <path d="M12 19v2" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>""",
        "list": """<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M8 6h13M8 12h13M8 18h13" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
          <path d="M3 6h.01M3 12h.01M3 18h.01" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
        </svg>""",
    }
    return icons.get(name, icons["list"])

def section_card(title: str, icon: str, badge: str | None = None, subtitle: str | None = None):
    badge_html = f'<span class="hec-badge">{badge}</span>' if badge else ""
    sub_html = f'<div class="hec-subtle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="hec-card"><div class="hec-title">{_svg(icon)}<span>{title}</span>{badge_html}</div>{sub_html}</div>',
        unsafe_allow_html=True
    )

APP_VERSION = "V22.0"

# --- CO2 (irányadó, finomítható később)
DEFAULT_GRID_CO2_KG_PER_KWH = 0.23
DEFAULT_GAS_CO2_KG_PER_KWH  = 0.202

# --- HU rezsi-küszöbök és árak (a felhasználó által megadottak)
ELEC = {
    "monthly_cap_kwh": 210.0,
    "day":   {"price_low": 36.386, "price_high": 70.104},
    "night": {"price_low": 22.962, "price_high": 60.935},
}
GAS = {
    "monthly_cap_m3": 144.0,
    "price_low_m3": 102.0,
    "price_high_m3": 747.0,
    "kwh_per_m3": 10.5,  # becslés; szolgáltatónként eltérhet
}

# --- Appliance defaults (irányadó)
FRIDGE_KWH_Y = {"új/hatékony": 180.0, "közepes": 280.0, "régi": 380.0}
STANDBY_W = {"alacsony": 30.0, "átlagos": 50.0, "magas": 80.0}
TV_W = {"LED": 100.0, "OLED": 130.0, "régi LCD/plazma": 200.0}

# Cooking
HOB_KWH_PER_COOK = {"elektromos (régi)": 1.8, "kerámia": 1.4, "indukció": 1.0}
OVEN_KWH_PER_USE = 2.5
GAS_HOB_M3_PER_COOK = 0.12

# --- Programs info (rövid, tájékoztató)
PROGRAM_SNIPPETS = {
    "attic_free": {
        "title": "Padlásfödém szigetelés – miért lehet „ingyenes”? (EKR/Hem jelleg)",
        "body": [
            "Egyes konstrukciókban az energia-megtakarítás (tanúsított) értéke finanszírozhatja a kivitelezés jelentős részét.",
            "Általában feltétel a megfelelő vastagság és kivitelezési minőség, valamint dokumentálás (anyag, fotók, nyilatkozatok).",
            "Mindig az aktuális hivatalos feltételek az irányadók; ez itt tájékoztató.",
        ],
        "watch": [
            "λ (hővezetési tényező): pl. 0,039 W/mK körüli anyagok jók",
            "vastagság: gyakran 20–30 cm a cél (helyzettől függ)",
            "páratechnika, kémény/kontaktusok környéke, járhatóság",
        ]
    }
}

# --- DB helpers
def get_admin_password() -> Optional[str]:
    try:
        return st.secrets.get("ADMIN_PASSWORD")
    except Exception:
        return os.getenv("ADMIN_PASSWORD")

def get_database_url() -> Optional[str]:
    try:
        return st.secrets.get("DATABASE_URL")
    except Exception:
        return os.getenv("DATABASE_URL")

def ensure_sqlite():
    conn = sqlite3.connect("audit.db", check_same_thread=False)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT,
        settlement TEXT,
        postcode TEXT,
        area_m2 REAL,
        occupants INTEGER,
        heating_type TEXT,
        dhw_type TEXT,
        elec_total_kwh_y REAL,
        gas_total_kwh_y REAL,
        solid_total_kwh_y REAL,
        co2_total_kg REAL,
        top1 TEXT,
        top2 TEXT,
        top3 TEXT
    )""")
    conn.commit()
    return conn

def db_insert(row: dict):
    # V11: lokális SQLite (Supabase/Postgres bekötés később 1 lépés)
    conn = ensure_sqlite()
    conn.execute("""
        INSERT INTO submissions (created_at, settlement, postcode, area_m2, occupants, heating_type, dhw_type,
            elec_total_kwh_y, gas_total_kwh_y, solid_total_kwh_y, co2_total_kg, top1, top2, top3)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        row["created_at"], row["settlement"], row["postcode"], row["area_m2"], row["occupants"],
        row["heating_type"], row["dhw_type"], row["elec_total_kwh_y"], row["gas_total_kwh_y"], row["solid_total_kwh_y"],
        row["co2_total_kg"], row["top1"], row["top2"], row["top3"]
    ))
    conn.commit()

def db_fetch_all() -> pd.DataFrame:
    conn = ensure_sqlite()
    return pd.read_sql("SELECT * FROM submissions ORDER BY id DESC", conn)

# --- Data helpers (település)
@st.cache_data
def load_postcodes() -> pd.DataFrame:
    try:
        df = pd.read_csv("hu_postcodes.csv", dtype={"postcode": str})
        df["postcode"] = df["postcode"].astype(str).str.zfill(4)
        df["settlement"] = df["settlement"].astype(str).str.strip()
        return df.dropna(subset=["postcode","settlement"])
    except Exception:
        return pd.DataFrame(columns=["postcode","settlement"])

@st.cache_data
def load_settlement_helper() -> pd.DataFrame:
    try:
        df = load_csv_cached("hu_settlements_helper.csv")
        df["settlement"] = df["settlement"].astype(str).str.strip()
        return df.dropna(subset=["settlement"]).drop_duplicates()
    except Exception:
        return pd.DataFrame(columns=["settlement"])

@st.cache_data
def load_population() -> pd.DataFrame:
    try:
        df = load_csv_cached("hu_settlements_population_2015.csv")
        df["settlement"] = df["settlement"].astype(str).str.strip()
        df["population_2015_01_01"] = pd.to_numeric(df["population_2015_01_01"], errors="coerce")
        return df.dropna(subset=["settlement"])
    except Exception:
        return pd.DataFrame(columns=["settlement","population_2015_01_01"])

POSTCODES_DF = load_postcodes()
SETT_HELPER = load_settlement_helper()
POP_DF = load_population()

def settlements_by_postcode(pc: str) -> List[str]:
    if POSTCODES_DF.empty:
        return []
    pc = str(pc).strip()
    if not (len(pc)==4 and pc.isdigit()):
        return []
    m = POSTCODES_DF[POSTCODES_DF["postcode"]==pc]
    return sorted(m["settlement"].dropna().unique().tolist())

def population_for_settlement(name: str) -> Optional[int]:
    if POP_DF.empty or not name:
        return None
    m = POP_DF[POP_DF["settlement"]==str(name).strip()]
    if m.empty:
        return None
    try:
        return int(m["population_2015_01_01"].iloc[0])
    except Exception:
        return None

# --- UI helpers
def settlement_sign(name: str | None):
    label = (name or "").strip()
    if not label:
        html = """
        <div style="display:flex;align-items:center;gap:10px;margin:6px 0 10px 0;">
          <div style="width:18px;height:18px;border:2px solid #bbb;border-radius:4px;"></div>
          <div style="padding:10px 14px;border:2px dashed #bbb;border-radius:10px;color:#777;">
            Település nincs megadva
          </div>
        </div>
        """
    else:
        html = f"""
        <div style="display:flex;align-items:center;gap:10px;margin:6px 0 10px 0;">
          <div style="width:18px;height:18px;background:#111;border-radius:4px;"></div>
          <div style="padding:10px 14px;border:2px solid #111;border-radius:10px;
                      font-weight:800;letter-spacing:0.5px;">
            {label.upper()}
          </div>
        </div>
        """
    st.markdown(html, unsafe_allow_html=True)

def card(title: str, body: str):
    st.markdown(f"""
    <div style="border:1px solid rgba(0,0,0,0.12);border-radius:14px;padding:14px 16px;margin:8px 0;">
      <div style="font-weight:800;font-size:16px;margin-bottom:6px;">{title}</div>
      <div style="color:rgba(0,0,0,0.75);line-height:1.35;">{body}</div>
    </div>
    """, unsafe_allow_html=True)

def fmt_huf(x: float) -> str:
    return f"{int(round(x)):,} Ft".replace(",", " ")

def fmt_kwh(x: float) -> str:
    return f"{x:,.0f} kWh".replace(",", " ")

def fmt_kg(x: float) -> str:
    return f"{x:,.0f} kg".replace(",", " ")

# --- Tariff back-calc
def backcalc_two_tier_from_cost(cost: float, cap_qty: float, price_low: float, price_high: float) -> Dict[str, float]:
    """Return qty_low, qty_high, qty_total, avg_price, extra_cost_vs_all_low."""
    if cost <= 0:
        return {"qty_low": 0.0, "qty_high": 0.0, "qty_total": 0.0, "avg_price": 0.0, "extra_cost": 0.0}
    max_low_cost = cap_qty * price_low
    if cost <= max_low_cost:
        qty = cost / price_low
        return {"qty_low": qty, "qty_high": 0.0, "qty_total": qty, "avg_price": price_low, "extra_cost": 0.0}
    rem = cost - max_low_cost
    qty_high = rem / price_high
    qty_total = cap_qty + qty_high
    # extra cost compared to if the high-part was billed at low price
    extra = qty_high * (price_high - price_low)
    avg = cost / qty_total if qty_total > 0 else 0.0
    return {"qty_low": cap_qty, "qty_high": qty_high, "qty_total": qty_total, "avg_price": avg, "extra_cost": extra}

def yearly_from_monthly(cost_month: float) -> float:
    return float(cost_month) * 12.0

# --- PDF
def make_pdf(summary: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    def line(x,y,s,bold=False,size=11):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x*mm, y*mm, s)
    y=285
    line(15,y,"Home Energy Check – Összefoglaló",bold=True,size=16); y-=10
    line(15,y,f"Verzió: {APP_VERSION}"); y-=6
    line(15,y,f"Dátum: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"); y-=10

    line(15,y,"Ingatlan",bold=True,size=13); y-=8
    for s in [
        f"Település: {summary.get('settlement','-')}  (IR: {summary.get('postcode','-')})",
        f"Alapterület: {int(summary.get('area_m2',0))} m²   Háztartás: {int(summary.get('occupants',0))} fő",
        f"Fűtés: {summary.get('heating_type','-')}   Melegvíz: {summary.get('dhw_type','-')}",
    ]:
        line(15,y,f"- {s}"); y-=6

    y-=4
    line(15,y,"Éves becslés",bold=True,size=13); y-=8
    line(15,y,f"- Villany: {fmt_kwh(summary.get('elec_kwh_y',0))}/év"); y-=6
    line(15,y,f"- Gáz: {fmt_kwh(summary.get('gas_kwh_y',0))}/év"); y-=6
    line(15,y,f"- Összes: {fmt_kwh(summary.get('total_kwh_y',0))}/év"); y-=6
    line(15,y,f"- CO₂: {fmt_kg(summary.get('co2_total_kg',0))}/év"); y-=10

    line(15,y,"TOP javaslatok",bold=True,size=13); y-=8
    for i,t in enumerate(summary.get("top",[])[:3], start=1):
        line(15,y,f"{i}. {t}"); y-=6

    y-=8
    c.setFont("Helvetica", 9)
    txt=("Tájékoztató becslés (tipikusan ±15–30%). Nem helyettesít hivatalos energetikai tanúsítványt/auditot. "
         "Árak és támogatások változhatnak.")
    c.drawString(15*mm, y*mm, txt[:115]); y-=5
    c.drawString(15*mm, y*mm, txt[115:])
    c.showPage(); c.save()
    return buf.getvalue()

# --- Page header (minimal)
st.markdown("""
<style>
.block-container {padding-top: 1.2rem;}
h1, h2, h3 {letter-spacing: -0.2px;}
</style>
""", unsafe_allow_html=True)

st.title(f"Energia & CO₂ Audit ({APP_VERSION})")
st.caption("Lakossági energia- és CO₂ audit (tájékoztató becslés). Ft-ból visszafejtett rezsiküszöbös számolással.")

tabs = st.tabs(["Kitöltés", "Admin"])

with tabs[0]:
    left, right = st.columns([1,1])

    # --- LEFT
    with left:
        st.subheader("Hely (opcionális)")
        postcode = st.text_input("Irányítószám (4 számjegy)", value="", placeholder="pl. 6720")
        cand = settlements_by_postcode(postcode) if postcode else []
        settlement = ""
        if cand:
            settlement = st.selectbox("Talált település(ek)", cand, index=0)
        use_list = st.checkbox("Település kiválasztása listából", value=(not bool(settlement)))
        if use_list and not settlement:
            if SETT_HELPER.empty:
                settlement = st.text_input("Település neve", value="")
            else:
                settlement = st.selectbox("Település", SETT_HELPER["settlement"].tolist(), index=0)

        settlement_sign(settlement)

        pop = population_for_settlement(settlement)
        if pop is not None:
            st.caption(f"Lakosság (2015): {pop:,} fő".replace(",", " "))

        st.subheader("Alap adatok")
        area_m2 = st.number_input("Alapterület (m²)", min_value=20, max_value=600, value=100, step=5)
        occupants = st.number_input("Háztartás létszáma (fő)", min_value=1, max_value=12, value=3, step=1)

        with st.expander("Épületszerkezet (haladó / opcionális)", expanded=False):
            insulation_level = st.selectbox("Szigetelés általános állapota", ["Nem tudom", "gyenge", "közepes", "jó"], index=0)
            wall_type = st.selectbox("Falazat típusa", ["Nem tudom", "Vályog", "Tégla", "B30", "Ytong", "Vegyes", "Egyéb"], index=0)
            wall_thickness_cm = st.number_input("Falvastagság (cm)", min_value=0, value=0, step=1)
            has_facade = st.selectbox("Homlokzati szigetelés", ["Nem tudom", "nincs", "van"], index=0)
            facade_type = "—"; facade_cm = 0
            if has_facade == "van":
                facade_type = st.selectbox("Szigetelés típusa", ["EPS 0.039", "Grafitos EPS", "Kőzetgyapot", "Egyéb"], index=0)
                facade_cm = st.number_input("Szigetelés vastagság (cm)", min_value=0, value=12, step=1)

        with st.expander("Nyílászárók (opcionális)", expanded=False):
            frame = st.selectbox("Keret", ["Nem tudom", "Fa", "Műanyag", "Alumínium", "Vegyes"], index=0)
            glazing = st.selectbox("Üvegezés", ["Nem tudom", "1 réteg", "2 réteg", "3 réteg"], index=0)
            install_year = st.number_input("Beépítés éve (ha ismert)", min_value=1900, max_value=2100, value=0, step=1)
            shutter_box = st.selectbox("Beépített redőnytok?", ["Nem tudom", "nincs", "van"], index=0)

    # --- RIGHT
    with right:
        st.subheader("Fűtés és melegvíz")
        heating_type = st.selectbox("Fűtés típusa", [
            "Nem tudom",
            "Gáz konvektor",
            "Gáz kazán (kombi)",
            "Gáz kazán (csak fűtés)",
            "Elektromos radiátor / Nobo / fűtőpanel",
            "Elektromos padlófűtés",
            "Klíma (hűtő-fűtő)",
            "Vegyes tüzelés (fa/szén)"
        ], index=0)

        dhw_type = st.selectbox("Melegvíz (HMV) energiaforrás", [
            "Nem tudom",
            "Villanybojler (nappali)",
            "Villanybojler (éjszakai/vezérelt)",
            "Gáz (kombi)",
            "Gáz vízmelegítő",
            "Egyéb"
        ], index=0)

        # Electricity input
        st.subheader("Villany (Ft alapján – ajánlott)")
        elec_mode = st.radio("Megadás", ["Ft/hó", "Ft/év", "Haladó: kWh/év"], horizontal=True, index=0)
        elec_cost_y = 0.0
        if elec_mode == "Ft/hó":
            elec_cost_y = yearly_from_monthly(st.number_input("Villany összesen (Ft/hó)", min_value=0.0, value=0.0, step=500.0))
        elif elec_mode == "Ft/év":
            elec_cost_y = st.number_input("Villany összesen (Ft/év)", min_value=0.0, value=0.0, step=5000.0)
        else:
            elec_kwh_y_manual = st.number_input("Villany összesen (kWh/év)", min_value=0.0, value=0.0, step=100.0)
            # approximate cost by blending (for display only)
            elec_cost_y = 0.0

        has_night_meter = st.checkbox("Van éjszakai / vezérelt mérő?", value=False)
        night_cost_y = 0.0
        if has_night_meter:
            st.caption("Ha nem tudod külön az éjszakai összeget, hagyd üresen → nappali tarifával számolunk.")
            night_mode = st.radio("Éjszakai megadás", ["Nem adom meg", "Ft/hó", "Ft/év"], horizontal=True, index=0)
            if night_mode == "Ft/hó":
                night_cost_y = yearly_from_monthly(st.number_input("Éjszakai villany (Ft/hó)", min_value=0.0, value=0.0, step=500.0))
            elif night_mode == "Ft/év":
                night_cost_y = st.number_input("Éjszakai villany (Ft/év)", min_value=0.0, value=0.0, step=5000.0)

        # Gas input
        st.subheader("Gáz (Ft alapján – ha van)")
        gas_mode = st.radio("Gáz megadás", ["Nincs gáz", "Ft/hó", "Ft/év", "Haladó: m³/év"], horizontal=True, index=0)
        gas_cost_y = 0.0
        gas_m3_y_manual = 0.0
        if gas_mode == "Ft/hó":
            gas_cost_y = yearly_from_monthly(st.number_input("Gáz összesen (Ft/hó)", min_value=0.0, value=0.0, step=1000.0))
        elif gas_mode == "Ft/év":
            gas_cost_y = st.number_input("Gáz összesen (Ft/év)", min_value=0.0, value=0.0, step=10000.0)
        elif gas_mode == "Haladó: m³/év":
            gas_m3_y_manual = st.number_input("Gáz (m³/év)", min_value=0.0, value=0.0, step=10.0)

        # Advanced: heating appliance details
        with st.expander("Fűtés részletek (haladó, opcionális)", expanded=False):
            conv_count = 0
            el_rad_count = 0
            el_rad_kw = 0.0
            el_rad_hours = 0.0
            floor_m2 = 0.0
            floor_wm2 = 0.0
            clim_count = 0
            clim_scop = 3.5
            if heating_type == "Gáz konvektor":
                conv_count = st.number_input("Konvektorok száma", min_value=0, value=3, step=1)
            elif "Elektromos radiátor" in heating_type:
                el_rad_count = st.number_input("Radiátorok száma", min_value=0, value=3, step=1)
                el_rad_kw = st.selectbox("Átlagos teljesítmény (kW/db)", [0.75, 1.0, 1.5, 2.0, 0.0], index=2, format_func=lambda x: "Nem tudom" if x==0.0 else f"{x} kW")
                el_rad_hours = st.selectbox("Napi átlagos fűtési idő", [4,6,8,0], index=1, format_func=lambda x: "Nem tudom" if x==0 else f"{x} óra/nap")
            elif heating_type == "Elektromos padlófűtés":
                floor_m2 = st.number_input("Fűtött terület (m²)", min_value=0.0, value=float(max(20, area_m2*0.6)), step=5.0)
                floor_wm2 = st.selectbox("Teljesítmény-sűrűség", [80,100,120,0], index=1, format_func=lambda x: "Nem tudom" if x==0 else f"{x} W/m²")
            elif "Klíma" in heating_type:
                clim_count = st.number_input("Klímák száma", min_value=0, value=1, step=1)
                clim_scop = st.selectbox("Átlagos SCOP", [3.0,3.5,4.0], index=1)

        # DHW details
        with st.expander("Melegvíz részletek (haladó, opcionális)", expanded=False):
            boiler_l = 0
            dhw_use = "átlagos"
            if "Villanybojler" in dhw_type:
                boiler_l = st.selectbox("Bojler térfogat", [80, 120, 160, 0], index=1, format_func=lambda x: "Nem tudom" if x==0 else f"{x} liter")
                dhw_use = st.selectbox("Melegvíz használat", ["alacsony","átlagos","magas"], index=1)

        
        st.subheader("Villamos csatlakozás (opcionális)")
        supply = st.selectbox("Jelenlegi csatlakozás", ["Nem tudom","1×16 A","1×32 A","3×16 A","3×20 A","3×25 A"], index=0)
        with st.expander("Jövőbeni tervek (opcionális)", expanded=False):
            plan_solar = st.checkbox("Tervezel napelemet 1–3 éven belül?", value=False)
            plan_ev = st.checkbox("Tervezel elektromos autót 3–5 éven belül?", value=False)
            plan_hp = st.checkbox("Tervezel hőszivattyút/klímás fűtést bővíteni?", value=("Klíma" in heating_type))
            phase_balance_note = st.selectbox("Vannak nagyfogyasztók egyszerre (sütő+indukció+bojler/klíma)?", ["Nem tudom","ritkán","gyakran"], index=0)
            planned_ev = st.checkbox("Tervezel elektromos autó töltést (wallbox)?", value=False)
            if planned_ev:
                charger_kw = st.selectbox("Tervezett töltési teljesítmény", ["3.6 kW (1×16A)","7.4 kW (1×32A)","11 kW (3×16A)"], index=2)
            else:
                charger_kw = None
            st.markdown("**Bővítés / mérőhely költségek (opcionális):**")
            amp_fee_ft = st.number_input("Hozzájárulás / amper bővítés díja (Ft)", min_value=0, value=79000, step=1000)
            cabinet_ft = st.number_input("Mérőhely/szekrény szerelés (Ft)", min_value=0, value=350000, step=10000)
            st.caption("Tipp: ha sok nagy fogyasztód van, érdemes a fázisokat jól elosztani; néha a 3×16A helyett egyik fázis 20A-ra emelése praktikus lehet (helyi szolgáltatói lehetőségek szerint).")


        section_card("Állandó és napi fogyasztók", "list", subtitle="Becslések: hűtő, standby, főzés, napi rutin")
        with st.expander("Hűtők / standby / TV", expanded=False):
            fridge_n = st.selectbox("Hűtő/fagyasztó darabszám", [0,1,2,3], index=1, format_func=lambda x: "3+" if x==3 else str(x))
            fridge_age = st.selectbox("Hűtők kora/hatékonysága", ["Nem tudom", "új/hatékony", "közepes", "régi"], index=0)
            standby_level = st.selectbox("Standby terhelés", ["Nem tudom","alacsony","átlagos","magas"], index=0)
            tv_has = st.checkbox("Van TV?", value=True)
            tv_hours = 0
            tv_type = "LED"
            if tv_has:
                tv_hours = st.selectbox("TV használat (óra/nap)", [2,4,6], index=1)
                tv_type = st.selectbox("TV típusa", ["LED","OLED","régi LCD/plazma"], index=0)

        with st.expander("Főzés és sütés (opcionális)", expanded=False):
            hob_type = st.selectbox("Főzőlap", ["Nem tudom","Gáz főzőlap","Indukció","Kerámia","Elektromos (régi)"], index=0)
            cook_freq = st.selectbox("Főzés gyakoriság", ["Ritkán (heti 2–3)", "Átlagos (napi 1)", "Gyakori (napi 2+)"], index=1)
            oven_count = st.selectbox("Elektromos sütő darabszám", [0,1,2], index=1)
            oven_use = st.selectbox("Sütő használat", ["Ritkán (heti 1)", "Átlagos (heti 2–3)", "Gyakori (szinte naponta)"], index=1)

        st.subheader("CO₂ tényezők (haladó)")
        grid_co2 = st.number_input("Áram CO₂ (kg/kWh)", min_value=0.01, max_value=1.0, value=float(DEFAULT_GRID_CO2_KG_PER_KWH), step=0.01)
        gas_co2  = st.number_input("Gáz CO₂ (kg/kWh)", min_value=0.05, max_value=0.5, value=float(DEFAULT_GAS_CO2_KG_PER_KWH), step=0.001)

    st.divider()
    st.subheader("Eredmény")

    # --- Compute electricity kWh from cost using HU tiers (month-based)
    elec_kwh_y = 0.0
    day_detail = {"qty_low":0,"qty_high":0,"qty_total":0,"avg_price":0,"extra_cost":0}
    night_detail = {"qty_low":0,"qty_high":0,"qty_total":0,"avg_price":0,"extra_cost":0}

    if elec_mode == "Haladó: kWh/év":
        elec_kwh_y = float(elec_kwh_y_manual)
    else:
        # Split annual cost into monthly average cost for tier logic (approx)
        day_cost_y = max(0.0, elec_cost_y - night_cost_y)
        day_cost_m = day_cost_y / 12.0 if day_cost_y > 0 else 0.0
        day_detail = backcalc_two_tier_from_cost(day_cost_m, ELEC["monthly_cap_kwh"], ELEC["day"]["price_low"], ELEC["day"]["price_high"])
        day_kwh_m = day_detail["qty_total"]
        elec_kwh_y += day_kwh_m * 12.0

        if has_night_meter and night_cost_y > 0:
            night_cost_m = night_cost_y / 12.0
            night_detail = backcalc_two_tier_from_cost(night_cost_m, ELEC["monthly_cap_kwh"], ELEC["night"]["price_low"], ELEC["night"]["price_high"])
            elec_kwh_y += night_detail["qty_total"] * 12.0

    # --- Appliances add-on (only if user filled; but even with zero costs it can estimate baseline; keep conservative)
    appliance_kwh_y = 0.0
    if 'fridge_n' in locals():
        if fridge_n > 0:
            if fridge_age in FRIDGE_KWH_Y:
                appliance_kwh_y += float(fridge_n) * FRIDGE_KWH_Y[fridge_age]
            else:
                appliance_kwh_y += float(fridge_n) * FRIDGE_KWH_Y["közepes"]
        if standby_level in STANDBY_W:
            w = STANDBY_W[standby_level]
            appliance_kwh_y += (w/1000.0) * 24.0 * 365.0
        elif standby_level == "Nem tudom":
            appliance_kwh_y += (STANDBY_W["átlagos"]/1000.0) * 24.0 * 365.0
        if tv_has:
            w = TV_W.get(tv_type, 100.0)
            appliance_kwh_y += (w/1000.0) * float(tv_hours) * 365.0

        # Cooking
        cook_per_week = {"Ritkán (heti 2–3)": 2.5, "Átlagos (napi 1)": 7.0, "Gyakori (napi 2+)": 14.0}[cook_freq]
        if hob_type in ["Indukció","Kerámia","Elektromos (régi)"]:
            key = {"Indukció":"indukció","Kerámia":"kerámia","Elektromos (régi)":"elektromos (régi)"}[hob_type]
            appliance_kwh_y += HOB_KWH_PER_COOK[key] * cook_per_week * 52.0
        elif hob_type == "Gáz főzőlap":
            # gas add later
            pass

        oven_per_week = {"Ritkán (heti 1)": 1.0, "Átlagos (heti 2–3)": 2.5, "Gyakori (szinte naponta)": 6.0}[oven_use]
        appliance_kwh_y += float(oven_count) * OVEN_KWH_PER_USE * oven_per_week * 52.0

    # We'll not double count: if user provided costs, appliances are already included in total. So only add appliance estimate when user gave zero cost (or haladó kWh).
    # Practical: show appliance estimate separately; keep totals based on provided costs/kWh. We'll show both.
    elec_kwh_y_total_used = elec_kwh_y if elec_kwh_y > 0 else appliance_kwh_y

    # --- Gas kWh from cost/m3
    gas_kwh_y = 0.0
    gas_detail = {"qty_low":0,"qty_high":0,"qty_total":0,"avg_price":0,"extra_cost":0}
    gas_m3_y = 0.0
    if gas_mode == "Haladó: m³/év":
        gas_m3_y = float(gas_m3_y_manual)
    elif gas_mode in ["Ft/hó","Ft/év"]:
        gas_cost_m = (gas_cost_y/12.0) if gas_cost_y>0 else 0.0
        gas_detail = backcalc_two_tier_from_cost(gas_cost_m, GAS["monthly_cap_m3"], GAS["price_low_m3"], GAS["price_high_m3"])
        gas_m3_y = gas_detail["qty_total"] * 12.0

    # Cooking gas hob
    if 'hob_type' in locals() and hob_type == "Gáz főzőlap":
        cook_per_week = {"Ritkán (heti 2–3)": 2.5, "Átlagos (napi 1)": 7.0, "Gyakori (napi 2+)": 14.0}[cook_freq]
        gas_m3_y += GAS_HOB_M3_PER_COOK * cook_per_week * 52.0

    gas_kwh_y = gas_m3_y * GAS["kwh_per_m3"]

    # --- Simple split heating vs dhw (for messaging only)
    # If dhw is electric, note; if gas combo, note. Not used heavily yet.
    # CO2
    co2_total = (elec_kwh_y_total_used * grid_co2) + (gas_kwh_y * gas_co2)

    total_kwh_y = elec_kwh_y_total_used + gas_kwh_y

    # Metrics
    m1,m2,m3,m4 = st.columns(4)
    m1.metric("Villany (becslés)", f"{fmt_kwh(elec_kwh_y_total_used)}/év")
    m2.metric("Gáz (becslés)", f"{fmt_kwh(gas_kwh_y)}/év")
    m3.metric("Összes energia", f"{fmt_kwh(total_kwh_y)}/év")
    per_cap = co2_total / max(1, int(occupants))
    m4.metric("CO₂ / fő", f"{fmt_kg(per_cap)}/év")

    # Rezsi detail (only if costs provided)
    with st.expander("Rezsiküszöb bontás (részletek)", expanded=False):
        if elec_mode != "Haladó: kWh/év" and elec_cost_y > 0:
            st.write("**Villany – nappali (A1) becslés:**")
            st.write(f"- Kedvezményes: {day_detail['qty_low']*12:.0f} kWh/év")
            st.write(f"- Emelt: {day_detail['qty_high']*12:.0f} kWh/év")
            st.write(f"- Emelt tarifa „felár”: ~{fmt_huf(day_detail['extra_cost']*12)} / év")
            if has_night_meter and night_cost_y > 0:
                st.write("**Villany – éjszakai/vezérelt becslés:**")
                st.write(f"- Kedvezményes: {night_detail['qty_low']*12:.0f} kWh/év")
                st.write(f"- Emelt: {night_detail['qty_high']*12:.0f} kWh/év")
                st.write(f"- Emelt tarifa „felár”: ~{fmt_huf(night_detail['extra_cost']*12)} / év")
        else:
            st.info("Villanynál most kWh/év megadást használsz, ezért a rezsiküszöb bontás nem számolható Ft-ból.")
        if gas_mode in ["Ft/hó","Ft/év"] and gas_cost_y > 0:
            st.write("**Gáz becslés:**")
            st.write(f"- Kedvezményes: {gas_detail['qty_low']*12:.0f} m³/év")
            st.write(f"- Emelt: {gas_detail['qty_high']*12:.0f} m³/év")
            st.write(f"- Emelt tarifa „felár”: ~{fmt_huf(gas_detail['extra_cost']*12)} / év")

        if appliance_kwh_y > 0:
            st.write("**Becsült készülék-fogyasztás (tájékoztató):**")
            st.write(f"- Összesen ~{fmt_kwh(appliance_kwh_y)}/év (hűtő/standby/TV/főzés+sütés)")
            st.caption("Ha Ft-ból számoltál villanyt, ebben a költségben a készülékek már benne vannak; ezt inkább magyarázó bontásként kezeld.")

    # Recommendations (simple, V11 baseline)
    
    st.subheader("Javaslatok (TOP 3)")
    # --- Simple but actionable recommendation engine (V12 baseline)
    # Heating energy approximation: treat gas_kwh as heating+dhw; electric heating share if selected.
    heating_kwh_y = 0.0
    if gas_kwh_y > 0:
        if "Villanybojler" in dhw_type:
            heating_kwh_y += gas_kwh_y * 0.90
        else:
            heating_kwh_y += gas_kwh_y * 0.80
    if heating_type in ["Elektromos radiátor / Nobo / fűtőpanel", "Elektromos padlófűtés", "Klíma (hűtő-fűtő)"]:
        heating_kwh_y += max(0.0, elec_kwh_y_total_used * (0.35 if "Klíma" in heating_type else 0.55))

    avg_day_price = day_detail["avg_price"] if day_detail.get("avg_price",0)>0 else ELEC["day"]["price_low"]
    avg_night_price = night_detail["avg_price"] if night_detail.get("avg_price",0)>0 else ELEC["night"]["price_low"]
    avg_elec_price = avg_day_price
    if has_night_meter and night_cost_y>0 and elec_cost_y>0:
        day_cost_y = max(0.0, elec_cost_y - night_cost_y)
        avg_elec_price = (day_cost_y + night_cost_y) / max(1.0, elec_kwh_y) if elec_kwh_y>0 else avg_day_price
    avg_gas_price_per_kwh = (GAS["price_low_m3"]/GAS["kwh_per_m3"])

    def huf_from_kwh_heating(kwh: float) -> float:
        if gas_kwh_y >= (elec_kwh_y_total_used*0.6):
            return kwh * avg_gas_price_per_kwh
        return kwh * avg_elec_price

    attic_saving_frac = 0.18
    facade_saving_frac = 0.22
    attic_area = float(area_m2)
    facade_area = float(area_m2) * 2.5

    attic_unit_min, attic_unit_max = 6000.0, 12000.0
    facade_unit_min, facade_unit_max = 22000.0, 38000.0

    suggested_facade_cm = 15
    if wall_type in ["Ytong"]:
        suggested_facade_cm = 12
    if wall_type in ["Vályog","B30","Vegyes"]:
        suggested_facade_cm = 18
    if has_facade == "van" and 'facade_cm' in locals() and facade_cm >= 12:
        suggested_facade_cm = int(max(0, facade_cm))

    phase_rec = None
    if 'supply' in locals() and supply != "Nem tudom":
        if ('plan_ev' in locals() and plan_ev) or ('plan_hp' in locals() and plan_hp) or ('hob_type' in locals() and hob_type=="Indukció"):
            if supply in ["1×16 A","1×32 A"]:
                phase_rec = "3×20 A vagy 3×25 A (EV/klíma/indukció miatt)"
            elif supply == "3×16 A" and ('phase_balance_note' in locals() and phase_balance_note == "gyakran"):
                phase_rec = "3×20 A (több nagyfogyasztó egyidejű használata miatt)"

    phase_fee_min, phase_fee_max = 79000.0, 150000.0
    cabinet_min, cabinet_max = 350000.0, 450000.0

    pump_invest = 11200.0
    pump_save_y = 15000.0

    recs = []

    if insulation_level in ["gyenge","Nem tudom"]:
        attic_save_kwh = heating_kwh_y * attic_saving_frac
        attic_save_huf = huf_from_kwh_heating(attic_save_kwh)
        attic_cost_min = attic_area * attic_unit_min
        attic_cost_max = attic_area * attic_unit_max
        recs.append(("Padlásfödém szigetelés",
                     f"Ajánlás: 25–30 cm (λ≈0,039). Becsült megtakarítás: ~{fmt_kwh(attic_save_kwh)}/év (≈ {fmt_huf(attic_save_huf)}/év). "
                     f"Költség becslés: {fmt_huf(attic_cost_min)} – {fmt_huf(attic_cost_max)}. "
                     f"Egyes konstrukciókban (EKR (Energiahatékonysági Kötelezettségi Rendszer) jelleg) jelentős rész finanszírozható – feltételekhez kötött."))

    if has_facade in ["nincs","Nem tudom"]:
        facade_save_kwh = heating_kwh_y * facade_saving_frac
        facade_save_huf = huf_from_kwh_heating(facade_save_kwh)
        facade_cost_min = facade_area * facade_unit_min
        facade_cost_max = facade_area * facade_unit_max
        mat = "EPS (λ≈0,039)"
        if 'facade_type' in locals() and facade_type and facade_type != "—":
            mat = facade_type
        recs.append(("Homlokzati hőszigetelés",
                     f"Ajánlás: ~{suggested_facade_cm} cm {mat}. Becsült megtakarítás: ~{fmt_kwh(facade_save_kwh)}/év (≈ {fmt_huf(facade_save_huf)}/év). "
                     f"Költség becslés: {fmt_huf(facade_cost_min)} – {fmt_huf(facade_cost_max)}. "
                     f"Megjegyzés: pontosításhoz hőhidak/nyílászárók számítanak."))

    # 2b) Windows upgrade (if old/poor)
    try:
        win_quality = window_quality if 'window_quality' in locals() else "Nem tudom"
    except Exception:
        win_quality = "Nem tudom"
    if win_quality in ["régi (1990 előtt)", "közepes (1990–2010)", "Nem tudom"]:
        win_save_kwh = heating_kwh_y * 0.10
        win_save_huf = huf_from_kwh_heating(win_save_kwh)
        # very rough unit costs per m² of floor area proxy
        win_cost_min = float(area_m2) * 3500.0
        win_cost_max = float(area_m2) * 9000.0
        recs.append(("Nyílászáró korszerűsítés",
                     f"Ajánlás: 2–3 rétegű üvegezés, jó beépítés (hőhíd/redsőnytok figyelem). "
                     f"Becsült megtakarítás: ~{fmt_kwh(win_save_kwh)}/év (≈ {fmt_huf(win_save_huf)}/év). "
                     f"Költség becslés (nagyságrend): {fmt_huf(win_cost_min)} – {fmt_huf(win_cost_max)}."))


    if phase_rec:
        recs.append(("Villamos csatlakozás fejlesztése",
                     f"Javasolt irány: {phase_rec}. Tipikus költségek: hálózati hozzájárulás ~{fmt_huf(phase_fee_min)}–{fmt_huf(phase_fee_max)}, "
                     f"mérőszekrény+munka gyakran {fmt_huf(cabinet_min)}–{fmt_huf(cabinet_max)}. "
                     f"Érdemes előre méretezni EV/indukció/klíma mellett, hogy ne kelljen később újra bontani."))

    if appliance_kwh_y > 600:
        recs.append(("Állandó fogyasztók csökkentése",
                     f"A megadott készülékek becsült fogyasztása ~{fmt_kwh(appliance_kwh_y)}/év. "
                     f"Régi hűtő(ke)t érdemes kiváltani, standby-t okos elosztóval csökkenteni."))

    # 3b) Heating modernization (high level)
    if heating_type in ["Gáz konvektor", "Vegyes tüzelés (fa/szén)", "Elektromos radiátor / Nobo / fűtőpanel"]:
        # provide guidance rather than hard numbers
        tip = "Szigetelés után érdemes méretezni a fűtést. Konvektoroknál gyakran nagy a veszteség és a komfort is gyenge."
        if "Vegyes" in heating_type:
            tip = "Szilárd tüzelésnél a komfort, levegőminőség és munkaráfordítás is szempont; alternatíva lehet kondenzációs kazán vagy hőszivattyú (szigeteléssel)."
        if "Elektromos radiátor" in heating_type:
            tip = "Direkt elektromos fűtésnél a fogyasztás magas; alternatíva lehet klímás fűtés (jó SCOP) vagy hőszivattyú + korszerű szabályozás."
        recs.append(("Fűtés korszerűsítése (irány)",
                     f"{tip} Támogatások gyakran feltételekhez kötöttek (pl. energetikai felújítási programok, 3+3 jellegű konstrukciók). "
                     f"Pontos javaslathoz szakemberes felmérés szükséges."))


    if (day_detail["qty_high"] > 0) or (gas_detail["qty_high"] > 0):
        extra = (day_detail["extra_cost"] + (night_detail["extra_cost"] if night_detail else 0) + gas_detail["extra_cost"]) * 12.0
        recs.append(("Cél: visszaférni a kedvezményes sávba",
                     f"Az emelt tarifa becsült többlete: ~{fmt_huf(extra)}/év. "
                     f"Szigetelés + szabályozás + készülékcsere segíthet visszakerülni a kedvezményes sávba."))

    recs.append(("Gyors nyereség: vezérlés/automatika",
                 f"Példa: keringető szivattyú időzítés. Beruházás ~{fmt_huf(pump_invest)}, várható megtakarítás ~{fmt_huf(pump_save_y)}/év. "
                 f"Megtérülés: ~{pump_invest/max(1.0,pump_save_y):.1f} év."))

    def _est_save_huf(text: str) -> float:
        m = re.search(r"≈\s*([\d\s]+)\s*Ft/év", text)
        if not m:
            return 0.0
        return float(m.group(1).replace(" ",""))

    recs_sorted = sorted(recs, key=lambda t: _est_save_huf(t[1]), reverse=True)
    top3 = recs_sorted[:3]

    for i, (title, body) in enumerate(top3, start=1):
        card(f"{i}. {title}", body)

    # Program snippets
    st.subheader("Rövid segédlet")
    with st.expander(PROGRAM_SNIPPETS["attic_free"]["title"], expanded=False):
        for b in PROGRAM_SNIPPETS["attic_free"]["body"]:
            st.write(f"- {b}")
        st.write("**Mire figyelj:**")
        for w in PROGRAM_SNIPPETS["attic_free"]["watch"]:
            st.write(f"- {w}")

    # PDF
    st.subheader("Letöltés")
    pdf = make_pdf({
        "settlement": settlement or "-",
        "postcode": postcode or "-",
        "area_m2": area_m2,
        "occupants": occupants,
        "heating_type": heating_type,
        "dhw_type": dhw_type,
        "elec_kwh_y": elec_kwh_y_total_used,
        "gas_kwh_y": gas_kwh_y,
        "total_kwh_y": total_kwh_y,
        "co2_total_kg": co2_total,
        "top": [t for (t,_) in top3]
    })
    st.download_button("PDF letöltése", data=pdf, file_name="home_energy_check_summary.pdf", mime="application/pdf")

    st.subheader("Anonim mentés (statisztikához)")
    if st.button("Mentés", type="primary"):
        db_insert({
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
            "settlement": settlement or "",
            "postcode": postcode or "",
            "area_m2": float(area_m2),
            "occupants": int(occupants),
            "heating_type": heating_type,
            "dhw_type": dhw_type,
            "elec_total_kwh_y": float(elec_kwh_y_total_used),
            "gas_total_kwh_y": float(gas_kwh_y),
            "solid_total_kwh_y": 0.0,
            "co2_total_kg": float(co2_total),
            "top1": top3[0][0] if len(top3)>0 else "",
            "top2": top3[1][0] if len(top3)>1 else "",
            "top3": top3[2][0] if len(top3)>2 else "",
        })
        st.success("Mentve ✅")

with tabs[1]:
    st.subheader("Admin statisztika")
    admin_pw = get_admin_password()
    if not admin_pw:
        st.info("ADMIN_PASSWORD nincs beállítva a Secrets-ben (Streamlit Cloud).")
    pw = st.text_input("Jelszó", type="password")
    if admin_pw and pw == admin_pw:
        st.success("Belépve ✅")
        df_all = db_fetch_all()
        if df_all.empty:
            st.info("Még nincs kitöltés.")
        else:
            st.metric("Összes kitöltés", int(df_all.shape[0]))
            st.dataframe(df_all.head(100), use_container_width=True)
            st.download_button("CSV letöltés", data=df_all.to_csv(index=False).encode("utf-8"),
                               file_name="submissions.csv", mime="text/csv")
    elif pw and admin_pw:
        st.error("Hibás jelszó.")


st.divider()
st.subheader("Számítás (V20 motor)")

with st.expander("Alap bemenetek", expanded=True):
    area_m2 = st.number_input("Alapterület (m²)", min_value=10.0, max_value=800.0, value=100.0, step=1.0)
    people = st.number_input("Lakók száma", min_value=1, max_value=12, value=3, step=1)
    annual_electric_cost = st.number_input("Villanyszámla (Ft/év) – ha tudod", min_value=0.0, value=0.0, step=1000.0)
    annual_gas_m3 = st.number_input("Gázfogyasztás (m³/év) – ha tudod", min_value=0.0, value=0.0, step=10.0)
    annual_gas_cost = st.number_input("Gázszámla (Ft/év) – ha m³ nincs", min_value=0.0, value=0.0, step=1000.0)

    wall_quality = st.selectbox("Falazat / szigetelés állapota (becslés)", ["Nem tudom","rossz","közepes","jó"], index=0)
    attic_quality = st.selectbox("Padlásfödém / födém szigetelése (becslés)", ["Nem tudom","rossz","közepes","jó"], index=0)
    window_quality = st.selectbox("Nyílászárók állapota (becslés)", ["Nem tudom","régi (1990 előtt)","közepes (1990–2010)","jó (2010 után)"], index=0)

    heating_type = st.selectbox("Fűtés típusa", ["Gáz kazán","Gáz konvektor","Klíma / hőszivattyú","Elektromos radiátor / Nobo / fűtőpanel","Nem tudom"], index=0)
    dhw_type = st.selectbox("Melegvíz típusa", ["Villanybojler","Gáz (kombi kazán / átfolyós)","Vegyes / nem tudom"], index=0)

    standby_w = st.number_input("Állandó fogyasztók (standby + szivattyú) átlag W", min_value=0.0, value=60.0, step=1.0)
    fridge_count = st.number_input("Hűtők száma", min_value=0, max_value=6, value=2, step=1)

    st.markdown("#### Fotók feltöltése (opcionális)")
    photo_files = st.file_uploader("Tölts fel 1–2 képet (padlás/kazán/ablak)", type=["png","jpg","jpeg","webp"], accept_multiple_files=True)

property_type = st.text_input("Ingatlan típusa (opcionális)", value="")
build_year = st.text_input("Építés éve / korszak (opcionális)", value="")
zip_code = st.text_input("Irányítószám (opcionális)", value="")
town = st.text_input("Település (opcionális)", value="")
address = st.text_input("Cím (opcionális)", value="")
coupon_code = st.text_input("Kuponkód (opcionális)", value="")

photo_bytes = []
if 'photo_files' in locals() and photo_files:
    for pf in photo_files[:2]:
        try:
            photo_bytes.append(pf.getvalue())
        except Exception:
            pass

inputs = dict(
    area_m2=area_m2,
    people=people,
    annual_electric_cost=annual_electric_cost,
    annual_gas_m3=annual_gas_m3,
    annual_gas_cost=annual_gas_cost,
    wall_quality=wall_quality,
    attic_quality=attic_quality,
    window_quality=window_quality,
    heating_type=heating_type,
    dhw_type=dhw_type,
    standby_w=standby_w,
    fridge_count=fridge_count,
    property_type=property_type,
    build_year=build_year,
    zip=zip_code,
    town=town,
    address=address,
    coupon_code=coupon_code,
    date=time.strftime('%Y-%m-%d'),
)

if st.button("Számítás indítása", type="primary"):
    results = calculate(inputs)
    st.session_state["results_v20"] = results
    st.session_state["inputs_v20"] = inputs

if "results_v20" in st.session_state:
    results = st.session_state["results_v20"]
    inputs_saved = st.session_state.get("inputs_v20", inputs)

    st.subheader("Eredmények")
    col1, col2, col3 = st.columns(3)
    col1.metric("Energia (összes)", f"{results['energy_kwh']['total']:.0f} kWh/év")
    col2.metric("Költség (becsült)", f"{results['cost_huf']['total']:.0f} Ft/év")
    col3.metric("CO₂", f"{results['co2_kg']['total']:.0f} kg/év")

    st.caption(
        f"Módszer: {results['meta']['method']} | Épület minőség (becslés): {results['meta']['building_quality']} | "
        f"Villany forrás: {results['meta']['electricity_source']} | Fűtés forrás: {results['meta']['heating_source']}"
    )

    
    st.markdown("### Anonim statisztika (opcionális)")
    consent_anon = st.checkbox("Hozzájárulok, hogy az adataim anonimizált, statisztikai célú feldolgozásra kerüljenek.", value=False)
    st.caption("Ez segíthet települési szintű felmérésekben. Nem mentünk nevet, emailt, címet.")

    if st.button("Anonim eredmény mentése"):
        if not consent_anon:
            st.error("A mentéshez kérlek pipáld be a hozzájárulást.")
        else:
            # Build a minimal, GDPR-barát sor
            recs = results.get("recommendations", []) or []
            top_rec = recs[0].get("title","") if recs else ""
            # crude main_loss inference
            main_loss = "vegyes"
            if "föd" in top_rec.lower() or "padl" in top_rec.lower():
                main_loss = "fodem"
            elif "homlok" in top_rec.lower() or "fal" in top_rec.lower():
                main_loss = "fal"
            elif "nyíl" in top_rec.lower() or "ablak" in top_rec.lower():
                main_loss = "nyilaszarok"

            row = {
                "ym": inputs_saved.get("date","")[:7] if inputs_saved.get("date") else time.strftime("%Y-%m"),
                "zip": (inputs_saved.get("zip") or "").strip() or None,
                "town": (inputs_saved.get("town") or "").strip() or None,
                "property_type": (inputs_saved.get("property_type") or "").strip() or None,
                "area_band": area_band(float(inputs_saved.get("area_m2") or 0)),
                "build_era": build_era(inputs_saved.get("build_year")),
                "energy_class": results.get("energy_class_light"),
                "kwh_m2_band": kwh_m2_band(float(results.get("energy_kwh",{}).get("per_m2",0) or 0)),
                "co2_band": co2_band(float(results.get("co2_kg",{}).get("total",0) or 0)),
                "annual_cost_band": cost_band(float(results.get("cost_huf",{}).get("total",0) or 0)),
                "main_loss": main_loss,
                "top_recommendation": top_rec[:120] or None,
                "consent_anon": True,
            }
            ok, msg = supabase_insert("audit_submissions", row, use_service_role=False)
            if ok:
                st.success("Köszönjük! Az anonim statisztikai adat mentve.")
            else:
                st.warning(f"Nem sikerült menteni: {msg}. (Ha nincs beállítva Supabase, ez normális.)")

st.markdown("### TOP javaslatok")
    for r in top_recommendations(results):
        with st.container(border=True):
            st.markdown(f"**{r['title']}**")
            st.write(r.get("why",""))
            c1, c2, c3 = st.columns(3)
            c1.metric("Megtakarítás", f"{r.get('save_huf_y',0):.0f} Ft/év")
            c2.metric("Energia", f"{r.get('save_kwh_y',0):.0f} kWh/év")
            c3.metric("CO₂", f"{r.get('save_co2_kg_y',0):.0f} kg/év")
            st.caption(f"Várható megtérülés (nagyságrend): ~{r.get('payback_y',0):.0f} év")

    st.markdown("### Támogatások (lista)")
    supports = match_supports(inputs_saved, results)
    for s in supports:
        with st.container(border=True):
            st.markdown(f"**{s.get('name','')}**  — relevancia: {'⭐'*int(s.get('score',3))}")
            st.write(f"Fókusz: {s.get('focus','')}")
            st.caption(s.get("notes",""))

    st.markdown("### PDF riport")
    pdf_bytes = build_pdf_report(results, inputs_saved, photos=photo_bytes)
    st.download_button("PDF letöltése", data=pdf_bytes, file_name="energia_co2_gyorsjelentes.pdf", mime="application/pdf")

    st.markdown("### Szakembert kérek (opcionális)")
    st.caption("Ha kéred, a rendszer továbbít egy előszűrt érdeklődést (nem kötelező).")
    lead_name = st.text_input("Név (opcionális)", value="")
    lead_phone = st.text_input("Telefonszám (opcionális)", value="")
    lead_email = st.text_input("Email (opcionális)", value="")
    consent = st.checkbox("Hozzájárulok, hogy az adataimat a kapcsolatfelvétel céljából továbbítsa a rendszer.", value=False)

    payload = {
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "name": lead_name,
        "phone": lead_phone,
        "email": lead_email,
        "zip": inputs_saved.get("zip",""),
        "town": inputs_saved.get("town",""),
        "address": inputs_saved.get("address",""),
        "area_m2": inputs_saved.get("area_m2"),
        "energy_class": results.get("energy_class_light"),
        "top_issue": (results.get("recommendations") or [{}])[0].get("title",""),
        "annual_cost_huf": results.get("cost_huf",{}).get("total"),
        "co2_kg_y": results.get("co2_kg",{}).get("total"),
        "results": results,
        "inputs": inputs_saved,
    }

    webhook_url = None
    try:
        webhook_url = st.secrets.get("WEBHOOK_URL", None)
    except Exception:
        webhook_url = None
    if not webhook_url:
        webhook_url = os.environ.get("WEBHOOK_URL")

    colL, colR = st.columns([1,1])
    with colL:
        if st.button("Szakembert kérek", type="secondary"):
            if not consent:
                st.error("A továbbításhoz kérlek pipáld be a hozzájárulást.")
            else:
                # Mentés Supabase-be (opcionális)
                lead_row = {
                    "name": lead_name or None,
                    "phone": lead_phone or None,
                    "email": lead_email or None,
                    "zip": inputs_saved.get("zip","") or None,
                    "town": inputs_saved.get("town","") or None,
                    "address": inputs_saved.get("address","") or None,
                    "area_m2": inputs_saved.get("area_m2"),
                    "energy_class": results.get("energy_class_light"),
                    "top_issue": (results.get("recommendations") or [{}])[0].get("title",""),
                    "payload": payload,
                    "consent_lead": True,
                }
                lead_ok, lead_msg = supabase_insert("audit_leads", lead_row, use_service_role=False)
                if webhook_url and requests:
                    try:
                        r = requests.post(webhook_url, json=payload, timeout=10)
                        if 200 <= r.status_code < 300:
                            st.success("Kész! Továbbítottuk az érdeklődést.")
                        else:
                            st.warning(f"Nem sikerült elküldeni (HTTP {r.status_code}). Letöltheted az űrlapot és elküldheted manuálisan.")
                    except Exception as e:
                        st.warning("Hálózati hiba. Letöltheted az űrlapot és elküldheted manuálisan.")
                else:
                    st.info("Nincs beállítva WEBHOOK_URL. Letöltheted az érdeklődést és elküldheted manuálisan.")

    with colR:
        st.download_button("Érdeklődés letöltése (JSON)", data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                           file_name="erdeklodes.json", mime="application/json")



st.divider()
st.subheader("Admin – statisztika (csak neked)")
admin_pw = st.text_input("Admin jelszó", type="password")
expected_pw = None
try:
    expected_pw = st.secrets.get("ADMIN_PASSWORD", None)
except Exception:
    expected_pw = os.environ.get("ADMIN_PASSWORD")

if expected_pw and admin_pw and admin_pw == str(expected_pw):
    st.success("Admin mód aktív.")
    ok, data = supabase_select(
        "audit_submissions",
        "ym,zip,town,energy_class,main_loss,top_recommendation",
        limit=5000
    )
    if ok and isinstance(data, list):
        # simple aggregations
        import pandas as pd
        df = pd.DataFrame(data)
        if df.empty:
            st.info("Még nincs adat.")
        else:
            st.markdown("### Kitöltések száma (havi)")
            st.dataframe(df.groupby("ym").size().rename("db").reset_index().sort_values("ym"), use_container_width=True)

            st.markdown("### Besorolás megoszlás")
            st.dataframe(df["energy_class"].value_counts(dropna=False).rename_axis("osztály").reset_index(name="db"), use_container_width=True)

            st.markdown("### TOP veszteség")
            st.dataframe(df["main_loss"].value_counts(dropna=False).rename_axis("veszteség").reset_index(name="db"), use_container_width=True)

            st.markdown("### Település / irányítószám (TOP 20)")
            key = df["town"].fillna("") + " " + df["zip"].fillna("")
            top = key.value_counts().head(20).rename_axis("település/zip").reset_index(name="db")
            st.dataframe(top, use_container_width=True)
    else:
        st.warning(f"Nem sikerült statisztikát lekérni: {data}")
else:
    st.caption("Admin statisztikához állíts be ADMIN_PASSWORD-öt a Secrets-ben.")
