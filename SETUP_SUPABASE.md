# Supabase beállítás (V22)

## 1) Táblák létrehozása
Másold be a korábbi SQL sémát (audit_submissions + audit_leads) a Supabase **SQL Editor** részébe és futtasd.

## 2) Secrets (Streamlit Cloud)
A Streamlit Cloudban: **Settings → Secrets**

Minimum (mentéshez):
- SUPABASE_URL
- SUPABASE_ANON_KEY

Admin statisztikához ajánlott:
- SUPABASE_SERVICE_KEY
- ADMIN_PASSWORD

Példa:
```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_ANON_KEY = "eyJ..."
SUPABASE_SERVICE_KEY = "eyJ..."
ADMIN_PASSWORD = "valami_erős_jelszó"
```

## 3) Mit csinál az app?
- **Anonim mentés:** audit_submissions (csak ha bepipálják a hozzájárulást)
- **Lead mentés:** audit_leads (csak „Szakembert kérek” + hozzájárulás)

## 4) Biztonság
Javasolt a táblákon RLS (Row Level Security) és „insert-only” policy.
