Komplett felhős (Supabase) MVP + tanácskártyák + U-érték becslés
===============================================================

1) Supabase-ben hozd létre a táblát (public.submissions) a korábban küldött SQL-lel (top1_key..top3_key mezőkkel).
2) Streamlit Cloud → App Settings → Secrets (TOML):

DATABASE_URL="postgresql+psycopg2://USER:PASSWORD@HOST:5432/DATABASE"
ADMIN_PASSWORD="erősjelszó"

3) Repo fájlok:
- app.py
- requirements.txt
- support_rules.hu.yaml
- program_cards.hu.yaml
- insulation_advice.hu.yaml
- hu_settlements_helper.csv

4) Deploy → mobilról böngészőből használható. (Chrome → Add to Home Screen)

Megjegyzés:
- A program_cards.hu.yaml mintakártya. Az aktuális pályázati feltételeket később webes forrásból vagy admin felületen frissíteni kell.


ÚJ V2:
- program_catalog.hu.yaml: előszűrt támogatási program-kártyák
- kistelepülés checkbox (5000 fő alatt)
- nyílászáró Uw becslés blokk

V3:
- Programoknál 'Követelmények' blokk (számla, szakember, dokumentumok, audit)
- Bővített program katalógus (fűtéskorszerűsítés, hőszivattyú, napelem mintakártyák)

V5:
- Irányítószám alapú településfelismerés (hu_postcodes.csv). A csomagban mintafájl van; éleshez teljes irányítószám-listát tölts fel ugyanebbe a formátumba.

V6:
- Teljes országos irányítószám-adat (hu_postcodes.csv)
- Teljes településlista + lakosságszám (2015) → automatikus kistelepülés felismerés (≤5000 fő)

V7:
- 'Miért ezt a sorrendet javasoljuk?' blokk az eredménynél
- Admin: települési energetikai profil táblázat + 1 oldalas települési PDF
- Admin: 'Ha N ház megcsinálná…' szimuláció (CO2, kWh, Ft, támogatási igény)

V9 (nulláról, lokális adatgyűjtéssel):
- Szilárd tüzelés (fa/szén/lignit/brikett/vegyes) becslés
- Köztartozás előszűrés (tájékoztató)
- Fázisbővítés (feltételes)
- PDF letöltés
- Anonim mentés: audit.db (SQLite)

Streamlit Cloudhoz élesben javasolt Supabase/Postgres (DATABASE_URL), mert a lokális fájl nem tartós.
