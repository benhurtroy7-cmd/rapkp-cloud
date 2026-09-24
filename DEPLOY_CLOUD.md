# RAPKP v26 — host your own cloud (5 minutes, free)

The Android app asks **your** server first (`Cloud → Termux localhost:8000 → Gem Built-in`).
This folder *is* that server. Deploy it once, paste the URL in the app
(**Me → Cloud API URL → Save & Re-connect**) and the app is cloud-powered.

Endpoints (all token-gated — without `?token=…` they return **403**):
`GET /api/ask`, `GET /api/chart`, `GET /api/charts`, `POST /api/charts`,
`POST /api/bug-report`, `GET /api/bugs`, `POST /api/correction`, `GET /api/corrections`,
`GET /api/modes`, `GET /health`

## Option 1 — Koyeb (free web service, Docker)
1. Push this folder to a GitHub repo (or use Koyeb's "upload" deploy).
2. Koyeb → **Create App** → **GitHub** → pick the repo → Dockerfile detected.
3. Service port **8000**, expose as **HTTPS**. Add env var:
   `RAPKP_TOKEN=KVYezIWxlkS6bwKDAi4i1pT3l7PLNvO2` (or your own secret).
4. Deploy → copy the URL, e.g. `https://rapkp-v26-xxxx.koyeb.app`.
5. In the app: Me → Cloud API URL → paste → **Save & Re-connect** → chip shows **Cloud LIVE**.

## Option 2 — Render (free web service, Docker)
New → Web Service → Build from repo → Runtime **Docker** → port 8000 → same env var.

## Option 3 — Termux on the phone itself (always free, no signup)
```bash
cp -r rapkp_cloud ~/
bash ~/rapkp_cloud/termux_run.sh      # serves http://localhost:8000
```
Then in the app set Cloud API URL = `http://localhost:8000` (or leave it empty — Termux is
already the built-in fallback). Keep Termux running + battery "No restrictions".

## Option 4 — any VPS
```bash
pip install -r requirements.txt
PORT=8000 RAPKP_TOKEN=your-secret python3 server.py
```

## Notes
- Ephemeris: **JPL DE421** via Skyfield (MIT) — downloaded once (~17 MB) at first start.
- Data is stored in `data/rapkp.db` (charts, bugs, corrections, query log).
- Change the token with env `RAPKP_TOKEN` and the same value in the app (Me → Secret Token).
