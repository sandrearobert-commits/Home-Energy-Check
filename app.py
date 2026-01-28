# Energia & CO₂ Audit – 12 (adaptív, anonim, admin statisztika, PDF)
# Futás: streamlit run app.py
# Opcionális:
#  - ADMIN_PASSWORD (Streamlit Secrets / env)
#  - DATABASE_URL (Postgres / Supabase) – ha nincs, lokális SQLite-t használ

import os
import io
import sqlite3
import datetime as dt
from typing import Optional, Tuple, List

import pandas as pd
import numpy as np
import streamlit as st
import yaml

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

st.set_page_config(page_title="Energia & CO₂ Audit (V9)", page_icon="🏠", layout="wide")

APP_VERSION = "V12"
DEFAULT_GRID_CO2_KG_PER_KWH = 0.23   # irányadó, pilot
DEFAULT_GAS_CO2_KG_PER_KWH  = 0.202  # irányadó, pilot

SOLID = {
    "fa":      {"kwh_per_unit": 1900.0, "unit": "m³", "co2_per_unit_kg": 40.0,   "note": "fa: irányadó CO₂-egyenérték + légszennyezési kockázat"},
    "szen":    {"kwh_per_unit": 6500.0, "unit": "t",  "co2_per_unit_kg": 2400.0, "note": "szén: nagyon magas CO₂ + légszennyezés"},
    "lignit":  {"kwh_per_unit": 4000.0, "unit": "t",  "co2_per_unit_kg": 1200.0, "note": "lignit: magas CO₂ + légszennyezés"},
    "brikett": {"kwh_per_unit": 5000.0, "unit": "t",  "co2_per_unit_kg": 1600.0, "note": "brikett: magas CO₂ + légszennyezés"},
}

MICRO_ACTIONS = [
    {"key": "pump_timer", "title": "Keringető szivattyú időzítés/vezérlés", "ft": 15000, "why": "Ha a szivattyú folyamatosan megy, ez tipikusan gyors megtérülésű."},
    {"key": "thermostat", "title": "Termosztát és hőfokok finomhangolása", "ft": 0, "why": "1–2°C csökkentés sok háznál érezhető megtakarítás."},
    {"key": "dhw_temp", "title": "HMV hőfok csökkentése + csőszigetelés", "ft": 12000, "why": "A melegvíz vesztesége gyakran 'láthatatlan', mégis sokat visz."},
    {"key": "draft", "title": "Huzatcsökkentés (tömítések, ajtóseprű)", "ft": 8000, "why": "Olcsó komfortjavítás – főleg régi nyílászáróknál."},
]

MEASURE_DEFAULTS = {
    "pump_control": {"invest": 30000.0,  "typ": "villany"},
    "dhw_optimization": {"invest": 120000.0, "typ": "hő"},
    "attic_insulation": {"invest": 700000.0, "typ": "hő"},
    "window_upgrade": {"invest": 1600000.0, "typ": "hő"},
    "heat_pump": {"invest": 3800000.0, "typ": "hő"},
    "pv": {"invest": 2500000.0, "typ": "villany"},
    "phase_upgrade": {"invest": 250000.0, "typ": "villany"},
}

DONT_DO_YET = [
    {"key": "heat_pump", "title": "Hőszivattyú", "why": "Előbb csökkentsd a hőigényt (szigetelés/nyílászáró), különben drágább üzem és nagyobb rendszer kell."},
    {"key": "pv", "title": "Napelem", "why": "Ha a ház hőigénye magas, előbb a megtakarítás adja a legjobb Ft/CO₂ arányt. Napelem akkor üt, ha már ésszerű a fogyasztás."},
]

@st.cache_data
def load_postcodes() -> pd.DataFrame:
    try:
        df = pd.read_csv("hu_postcodes.csv", dtype={"postcode": str})
        df["postcode"] = df["postcode"].astype(str).str.zfill(4)
        df["settlement"] = df["settlement"].astype(str).str.strip()
        return df.dropna(subset=["postcode","settlement"])
    except Exception:
        return pd.DataFrame(columns=["postcode","settlement"])

POSTCODES_DF = load_postcodes()

@st.cache_data
def load_settlement_helper() -> pd.DataFrame:
    try:
        df = pd.read_csv("hu_settlements_helper.csv")
        df["settlement"] = df["settlement"].astype(str).str.strip()
        return df.dropna(subset=["settlement"]).drop_duplicates()
    except Exception:
        return pd.DataFrame(columns=["settlement"])

SETT_HELPER = load_settlement_helper()

@st.cache_data
def load_population() -> pd.DataFrame:
    try:
        df = pd.read_csv("hu_settlements_population_2015.csv")
        df["settlement"] = df["settlement"].astype(str).str.strip()
        df["population_2015_01_01"] = pd.to_numeric(df["population_2015_01_01"], errors="coerce")
        return df.dropna(subset=["settlement"])
    except Exception:
        return pd.DataFrame(columns=["settlement","population_2015_01_01"])

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
        heating_main TEXT,
        heating_kwh_year REAL,
        grid_kwh_year REAL,
        gas_kwh_year REAL,
        solid_kwh_year REAL,
        co2_total_kg REAL,
        top1_key TEXT,
        top2_key TEXT,
        top3_key TEXT
    )""")
    conn.commit()
    return conn

def db_insert(row: dict):
    # V9 nulláról: lokális SQLite. (Supabase/Postgres később 1 sor Secrets-szel.)
    conn = ensure_sqlite()
    conn.execute("""
        INSERT INTO submissions (created_at, settlement, postcode, area_m2, occupants, heating_main,
            heating_kwh_year, grid_kwh_year, gas_kwh_year, solid_kwh_year, co2_total_kg, top1_key, top2_key, top3_key)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        row["created_at"], row["settlement"], row["postcode"], row["area_m2"], row["occupants"], row["heating_main"],
        row["heating_kwh_year"], row["grid_kwh_year"], row["gas_kwh_year"], row["solid_kwh_year"], row["co2_total_kg"],
        row["top1_key"], row["top2_key"], row["top3_key"]
    ))
    conn.commit()

def db_fetch_all() -> pd.DataFrame:
    conn = ensure_sqlite()
    return pd.read_sql("SELECT * FROM submissions ORDER BY id DESC", conn)

def fmt_huf(x: float) -> str:
    return f"{int(round(x)):,} Ft".replace(",", " ")

def fmt_kg(x: float) -> str:
    return f"{x:,.0f} kg".replace(",", " ")

def fmt_kwh(x: float) -> str:
    return f"{x:,.0f} kWh".replace(",", " ")

def solid_amount_to_kwh_and_co2(kind: str, amount: float) -> Tuple[float,float,str]:
    meta = SOLID[kind]
    return amount*meta["kwh_per_unit"], amount*meta["co2_per_unit_kg"], meta["unit"]

def estimate_measure_kwh_save(key: str, heat_kwh: float, dhw_kwh: float, grid_kwh: float) -> float:
    if key == "pump_control":
        return 320.0
    if key == "dhw_optimization":
        return max(0.0, dhw_kwh*0.18)
    if key == "attic_insulation":
        return max(0.0, heat_kwh*0.20)
    if key == "window_upgrade":
        return max(0.0, heat_kwh*0.10)
    if key == "heat_pump":
        return max(0.0, heat_kwh*0.80)
    if key == "pv":
        return max(0.0, min(grid_kwh, 1800.0))
    return 0.0

def measure_saving(key: str, kwh_save: float, el_price: float, heat_price: float, grid_co2: float, heat_co2: float) -> Tuple[float,float,float]:
    invest = float(MEASURE_DEFAULTS[key]["invest"])
    typ = MEASURE_DEFAULTS[key]["typ"]
    if typ == "villany":
        return kwh_save*el_price, kwh_save*grid_co2, invest
    return kwh_save*heat_price, kwh_save*heat_co2, invest

def build_measures(ctx: dict) -> pd.DataFrame:
    heat_kwh = float(ctx["heating_kwh_year"])
    dhw_kwh  = float(ctx["dhw_kwh_year"])
    grid_kwh = float(ctx["grid_kwh_year"])
    el_price = float(ctx["el_price"])
    heat_price = float(ctx["heat_price"])
    grid_co2 = float(ctx["grid_co2"])
    heat_co2 = float(ctx["heat_co2"])

    measures = [
        ("pump_control", "Szivattyú vezérlés / időzítés"),
        ("dhw_optimization", "Melegvíz optimalizálás"),
        ("attic_insulation", "Padlásfödém szigetelés"),
        ("window_upgrade", "Nyílászáró fejlesztés"),
        ("heat_pump", "Hőszivattyú (feltételekkel)"),
        ("pv", "Napelem (feltételekkel)"),
    ]
    rows=[]
    for key,name in measures:
        kwh = estimate_measure_kwh_save(key, heat_kwh, dhw_kwh, grid_kwh)
        ft, co2, invest = measure_saving(key, kwh, el_price, heat_price, grid_co2, heat_co2)
        payback = invest/ft if ft>0 else np.nan
        rows.append({
            "Kulcs": key,
            "Intézkedés": name,
            "Becsült beruházás (Ft)": invest,
            "Megtakarítás (kWh/év)": kwh,
            "Megtakarítás (Ft/év)": ft,
            "CO₂ csökkenés (kg/év)": co2,
            "Megtérülés (év)": round(payback,1) if np.isfinite(payback) else np.nan
        })
    df=pd.DataFrame(rows)
    df["score"] = (df["Megtakarítás (Ft/év)"].fillna(0) / (df["Becsült beruházás (Ft)"].replace({0: np.nan}))).fillna(0) + (df["CO₂ csökkenés (kg/év)"].fillna(0)/2000.0)
    df=df.sort_values("score",ascending=False).drop(columns=["score"])
    return df

def choose_micro_action(has_pump: bool, windows_quality: str) -> dict:
    if has_pump:
        return MICRO_ACTIONS[0]
    if windows_quality in ["régi","vegyes"]:
        return MICRO_ACTIONS[3]
    return MICRO_ACTIONS[1]

def dont_do_yet(insulation_level: str) -> List[dict]:
    return DONT_DO_YET if insulation_level=="gyenge" else []

def recommend_phase_upgrade(top_keys: List[str], service_current: str) -> Optional[dict]:
    if ("heat_pump" in top_keys) or ("pv" in top_keys):
        if service_current.startswith("3×"):
            return None
        return {
            "current": service_current,
            "suggested": "3×16 A",
            "cost_ft": MEASURE_DEFAULTS["phase_upgrade"]["invest"],
            "time": "Ügyintézés 2–6 hét, kivitelezés jellemzően 1 nap (helyzetfüggő).",
            "note": "Egyes programokban a bővítés költségének egy része elszámolható lehet – mindig a hivatalos kiírás az irányadó.",
        }
    return None

def make_pdf(settlement: str, postcode: str, area_m2: int, occupants: int, heating_main: str, total_kwh: float, co2_total: float, top3: List[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    def line(x,y,s,bold=False,size=11):
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x*mm, y*mm, s)

    y=285
    line(15,y,"Energia & CO₂ Audit – összefoglaló",bold=True,size=16); y-=10
    line(15,y,f"Verzió: {APP_VERSION}"); y-=6
    line(15,y,f"Dátum: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}"); y-=10

    line(15,y,"Ingatlan (röviden)",bold=True,size=13); y-=8
    for s in [
        f"Település: {settlement or '-'} (irányítószám: {postcode or '-'})",
        f"Alapterület: {area_m2} m², Háztartás: {occupants} fő",
        f"Fő fűtés: {heating_main}",
    ]:
        line(15,y,f"- {s}"); y-=6

    y-=4
    line(15,y,"Becsült éves összkép",bold=True,size=13); y-=8
    line(15,y,f"- Összes energia: {fmt_kwh(total_kwh)}/év"); y-=6
    line(15,y,f"- CO₂: {fmt_kg(co2_total)}/év"); y-=10

    line(15,y,"TOP 3 javaslat",bold=True,size=13); y-=8
    for i,t in enumerate(top3, start=1):
        line(15,y,f"{i}. {t}"); y-=6

    y-=6
    c.setFont("Helvetica", 9)
    txt=("Tájékoztató jellegű becslés (tipikusan ±15–25%). Nem helyettesít hivatalos auditot/tanúsítványt. "
         "Támogatásoknál a hivatalos kiírás az irányadó.")
    c.drawString(15*mm, y*mm, txt[:115]); y-=5
    c.drawString(15*mm, y*mm, txt[115:])
    c.showPage(); c.save()
    return buf.getvalue()

st.title("🏠 Energia & CO₂ Audit (V9)")
st.caption("Ingyenes, anonim, mobilbarát. A számok tájékoztató jellegűek.")

tabs = st.tabs(["Kitöltés", "Admin (statisztika)"])

with tabs[0]:
    col1,col2 = st.columns([1,1])

    with col1:
        st.subheader("📍 Hely (opcionális)")
        postcode = st.text_input("Irányítószám (4 számjegy)", value="")
        cand = settlements_by_postcode(postcode) if postcode else []
        settlement_from_pc = ""
        if cand:
            settlement_from_pc = st.selectbox("Talált település(ek)", cand, index=0)
        use_helper = st.checkbox("Település kiválasztása listából", value=not bool(settlement_from_pc))
        settlement = settlement_from_pc
        if use_helper and not settlement_from_pc:
            if SETT_HELPER.empty:
                settlement = st.text_input("Település neve", value="")
            else:
                settlement = st.selectbox("Település", SETT_HELPER["settlement"].tolist(), index=0)

        pop = population_for_settlement(settlement)
        if pop is not None:
            st.caption(f"Lakosság (2015): {pop:,} fő".replace(",", " "))
            st.write("**Kistelepülés (≤5000):** " + ("✅ Igen" if pop<=5000 else "❌ Nem"))
        else:
            st.checkbox("5000 fő alatti település? (ha nem ismert)", value=False)

        st.subheader("🏠 Alap adatok")
        area_m2 = st.number_input("Ház alapterülete (m²)", min_value=20, max_value=600, value=100, step=5)
        occupants = st.number_input("Hány fő él a háztartásban?", min_value=1, max_value=12, value=3, step=1)
        insulation_level = st.selectbox("Szigetelés állapota", ["gyenge","közepes","jó"], index=0)
        windows_quality = st.selectbox("Nyílászárók", ["régi","vegyes","korszerű"], index=1)

        st.subheader("🧾 Jogosultsági előszűrés")
        arrears = st.selectbox("Lejárt köztartozás helyzete", ["nincs","rendezés alatt","van","nem tudom"], index=0)
        with st.expander("Részletek"):
            st.write("Sok támogatásnál feltétel lehet a köztartozás-mentesség. Ez itt csak tájékoztató előszűrés.")

    with col2:
        st.subheader("🔥 Fűtés és fogyasztás")
        heating_main = st.selectbox("Fő fűtés típusa", ["gáz","villany/klíma","fa (szilárd)","szén","lignit","brikett","vegyes (fa+szén/lignit)"], index=0)
        grid_kwh_year = st.number_input("Villany fogyasztás (kWh/év)", min_value=0, max_value=50000, value=2500, step=100)

        gas_kwh_year = 0.0
        solid_kwh_year = 0.0
        solid_co2_kg = 0.0
        heating_kwh_year = 0.0

        if heating_main == "gáz":
            gas_kwh_year = st.number_input("Gáz (fűtés+HMV) – kWh/év", min_value=0, max_value=120000, value=18000, step=500)
            heating_kwh_year = float(gas_kwh_year)*0.78
        elif heating_main == "villany/klíma":
            heating_kwh_year = float(grid_kwh_year)*0.60
        elif heating_main.startswith("fa"):
            fa_sav = st.selectbox("Fa mennyisége szezonban", ["5–7 m³","8–10 m³","11–15 m³","15+ m³","nem tudom"], index=0)
            m3 = {"5–7 m³":6.0,"8–10 m³":9.0,"11–15 m³":13.0,"15+ m³":18.0,"nem tudom":10.0}[fa_sav]
            solid_kwh_year, solid_co2_kg, _ = solid_amount_to_kwh_and_co2("fa", m3)
            heating_kwh_year = solid_kwh_year*0.80
        elif heating_main in ["szén","lignit","brikett"]:
            kind = {"szén":"szen","lignit":"lignit","brikett":"brikett"}[heating_main]
            sav = st.selectbox("Mennyit használsz szezonban?", ["1–2 t","3–4 t","5+ t","nem tudom"], index=0)
            t_ = {"1–2 t":1.5,"3–4 t":3.5,"5+ t":6.0,"nem tudom":3.0}[sav]
            solid_kwh_year, solid_co2_kg, _ = solid_amount_to_kwh_and_co2(kind, t_)
            heating_kwh_year = solid_kwh_year*0.80
            st.warning("Szilárd tüzelésnél a légszennyezés is jelentős lehet (PM).")
        else:
            share = st.slider("Kb. mennyi a fa aránya?", 0, 100, 60, 5)
            fa_m3 = 10.0*(share/100.0)
            coal_t = 3.0*((100-share)/100.0)
            k1,c1,_=solid_amount_to_kwh_and_co2("fa", fa_m3)
            k2,c2,_=solid_amount_to_kwh_and_co2("szen", coal_t)
            solid_kwh_year = k1+k2
            solid_co2_kg = c1+c2
            heating_kwh_year = solid_kwh_year*0.80
            st.warning("Vegyes tüzelésnél a légszennyezés jellemzően magasabb.")

        st.subheader("💧 Melegvíz (becslés)")
        dhw_level = st.selectbox("Melegvíz használat", ["alacsony","átlagos","magas"], index=1)
        dhw_kwh_year = {"alacsony":1200,"átlagos":1800,"magas":2600}[dhw_level]

        st.subheader("⚡ Villamos csatlakozás")
        service_current = st.selectbox("Jelenlegi csatlakozás", ["1×16 A","1×20 A","1×25 A","3×16 A","3×20 A","3×25 A"], index=0)
        has_pump = st.checkbox("Van szivattyú (padlófűtés/ker.) ami sokat megy?", value=True)

        st.subheader("💸 Irányadó árak")
        el_price = st.number_input("Villany ára (Ft/kWh)", min_value=10.0, max_value=300.0, value=70.0, step=1.0)
        heat_price = st.number_input("Hő ára (Ft/kWh) – gáz/fa/szilárd irányadó", min_value=5.0, max_value=200.0, value=25.0, step=1.0)

        with st.expander("CO₂ tényezők (Részletek)"):
            grid_co2 = st.number_input("Áram CO₂ (kg/kWh)", min_value=0.01, max_value=1.0, value=float(DEFAULT_GRID_CO2_KG_PER_KWH), step=0.01)
            gas_co2  = st.number_input("Gáz CO₂ (kg/kWh)", min_value=0.05, max_value=0.5, value=float(DEFAULT_GAS_CO2_KG_PER_KWH), step=0.001)
        if "grid_co2" not in locals():
            grid_co2 = float(DEFAULT_GRID_CO2_KG_PER_KWH)
        if "gas_co2" not in locals():
            gas_co2 = float(DEFAULT_GAS_CO2_KG_PER_KWH)

    st.divider()
    st.subheader("✅ Eredmény")

    total_kwh = float(grid_kwh_year) + float(gas_kwh_year) + float(solid_kwh_year)
    co2_grid = float(grid_kwh_year)*float(grid_co2)
    co2_gas  = float(gas_kwh_year)*float(gas_co2)
    co2_total = co2_grid + co2_gas + float(solid_co2_kg)

    heat_co2 = float(gas_co2) if heating_main=="gáz" else (float(solid_co2_kg)/float(solid_kwh_year) if solid_kwh_year>0 else float(gas_co2))

    ctx = {
        "heating_kwh_year": float(heating_kwh_year),
        "dhw_kwh_year": float(dhw_kwh_year),
        "grid_kwh_year": float(grid_kwh_year),
        "el_price": float(el_price),
        "heat_price": float(heat_price),
        "grid_co2": float(grid_co2),
        "heat_co2": float(heat_co2),
    }

    m1,m2,m3 = st.columns(3)
    m1.metric("Összes energia", fmt_kwh(total_kwh)+"/év")
    m2.metric("CO₂ becslés", fmt_kg(co2_total)+"/év")
    m3.metric("Fajlagos energia", f"{(total_kwh/area_m2):.1f} kWh/m²/év")

    with st.expander("Hogyan számoltuk? (Részletek)"):
        st.write(f"- Áram CO₂: {grid_co2} kg/kWh → {fmt_kg(co2_grid)}")
        st.write(f"- Gáz CO₂: {gas_co2} kg/kWh → {fmt_kg(co2_gas)}")
        if solid_kwh_year>0:
            st.write(f"- Szilárd tüzelés (irányadó): {fmt_kg(solid_co2_kg)}")
            st.caption("Szilárd tüzelésnél a légszennyezés is fontos tényező.")

    df = build_measures(ctx)
    top_keys = df["Kulcs"].head(3).tolist()
    micro = choose_micro_action(has_pump, windows_quality)

    st.write("### ⚡ Legkisebb lépés MOST (0–50 e Ft)")
    st.success(f"**{micro['title']}** – kb. {fmt_huf(micro['ft'])}")
    st.caption(micro["why"])

    st.write("### 🧭 Miért ezt a sorrendet javasoljuk?")
    for i,k in enumerate(top_keys, start=1):
        r = df[df["Kulcs"]==k].iloc[0].to_dict()
        st.markdown(f"**{i}. {r['Intézkedés']}**")
        st.write(f"- Éves megtakarítás: **{fmt_huf(r['Megtakarítás (Ft/év)'])}**")
        st.write(f"- CO₂ csökkenés: **{fmt_kg(r['CO₂ csökkenés (kg/év)'])}**")
        if isinstance(r.get("Megtérülés (év)"), (int,float)) and np.isfinite(r.get("Megtérülés (év)")):
            st.write(f"- Becsült megtérülés: **{r['Megtérülés (év)']} év**")
        with st.expander("Részletek / megjegyzések"):
            st.caption("Becslés: ±15–25% tipikus bizonytalanság.")

    dd = dont_do_yet(insulation_level)
    if dd:
        st.write("### ⛔ Mit NE csinálj még")
        for x in dd:
            st.warning(f"**{x['title']}** – {x['why']}")

    st.write("### 🗺️ 5 éves útiterv")
    top_names = df["Intézkedés"].head(3).tolist()
    st.markdown("**0–1 év:** " + " • ".join([top_names[0], micro["title"]]))
    st.markdown("**2–3 év:** " + " • ".join([top_names[1]]))
    st.markdown("**4–5 év:** " + " • ".join([top_names[2]]))

    st.write("### 📋 Részletes javaslat-táblázat")
    st.dataframe(df, use_container_width=True)

    phase = recommend_phase_upgrade(top_keys, service_current)
    if phase:
        st.write("### ⚡ Fázisbővítés (feltételes)")
        st.write(f"- Jelenlegi: **{phase['current']}**")
        st.write(f"- Javasolt: **{phase['suggested']}**")
        st.write(f"- Irányadó költség: **{fmt_huf(phase['cost_ft'])}**")
        st.caption(phase["time"])
        with st.expander("Részletek"):
            st.write(phase["note"])

    st.write("### 🧾 Jogosultsági megjegyzések (előszűrés)")
    if arrears == "van":
        st.error("A jelzett köztartozás miatt a klasszikus pályázatok egy része valószínűleg nem elérhető a rendezésig.")
        st.info("Egyes szolgáltatás-alapú megoldások (pl. EKR) ettől függetlenül elérhetők lehetnek.")
    elif arrears in ["rendezés alatt","nem tudom"]:
        st.warning("Egyes támogatások feltételesek. Érdemes a státuszt ellenőrizni a benyújtás előtt.")
    else:
        st.success("Alapszinten nincs jelzett köztartozás, így több támogatási irány is nyitott lehet.")

    st.divider()
    st.subheader("⬇️ Letölthető összefoglaló")
    pdf = make_pdf(settlement, postcode, int(area_m2), int(occupants), heating_main, total_kwh, co2_total, top_names)
    st.download_button("PDF letöltése", data=pdf, file_name="energia_co2_audit_osszegzes.pdf", mime="application/pdf")

    st.subheader("📌 Mentés (anonim statisztikához)")
    if st.button("Mentés (anonim)", type="primary"):
        db_insert({
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
            "settlement": settlement or "",
            "postcode": postcode or "",
            "area_m2": float(area_m2),
            "occupants": int(occupants),
            "heating_main": heating_main,
            "heating_kwh_year": float(heating_kwh_year),
            "grid_kwh_year": float(grid_kwh_year),
            "gas_kwh_year": float(gas_kwh_year),
            "solid_kwh_year": float(solid_kwh_year),
            "co2_total_kg": float(co2_total),
            "top1_key": top_keys[0] if len(top_keys)>0 else "",
            "top2_key": top_keys[1] if len(top_keys)>1 else "",
            "top3_key": top_keys[2] if len(top_keys)>2 else "",
        })
        st.success("Mentve ✅ (anonim, statisztikai célra)")

with tabs[1]:
    st.subheader("🔐 Admin belépés")
    admin_pw = get_admin_password()
    if not admin_pw:
        st.info("ADMIN_PASSWORD nincs beállítva (teszthez: env vagy Streamlit Secrets).")
    pw = st.text_input("Jelszó", type="password")
    if admin_pw and pw == admin_pw:
        st.success("Belépve ✅")
        df_all = db_fetch_all()
        if df_all.empty:
            st.info("Még nincs kitöltés.")
        else:
            st.metric("Összes kitöltés", int(df_all.shape[0]))
            last7 = (pd.to_datetime(df_all["created_at"]) >= (pd.Timestamp.now() - pd.Timedelta(days=7))).sum()
            st.metric("Utolsó 7 nap", int(last7))

            st.subheader("Település TOP 30")
            grp = df_all.groupby("settlement").agg(
                kitoltesek=("id","count"),
                atlag_co2_kg=("co2_total_kg","mean"),
            ).reset_index().sort_values("kitoltesek", ascending=False).head(30)
            grp["atlag_co2_kg"] = grp["atlag_co2_kg"].round(0)
            st.dataframe(grp, use_container_width=True)

            st.subheader("TOP javaslat kulcsok")
            tops = pd.concat([df_all["top1_key"], df_all["top2_key"], df_all["top3_key"]]).value_counts().reset_index()
            tops.columns = ["javaslat_kulcs","db"]
            st.dataframe(tops, use_container_width=True)

            st.download_button("CSV letöltés", data=df_all.to_csv(index=False).encode("utf-8"),
                               file_name="submissions.csv", mime="text/csv")
    elif pw and admin_pw:
        st.error("Hibás jelszó.")
