# Ghost Flight — Local README

This project shows live flight positions in a Mexico bounding box using OpenSky and a small Flask app.

What I added and where
- `app.py` — Flask app. New features added:
  - environment-driven credentials (`OPENSKY_CLIENT_ID`, `OPENSKY_CLIENT_SECRET`), optional MongoDB persistence (`MONGODB_URI`), and optional Zabbix settings (`ZABBIX_API`, `ZABBIX_USER`, `ZABBIX_PASS`).
  - `classify_flight()` uses `data/operator_mapping.json` for better cargo/commercial classification.
  - `/vuelos`, `/vuelos/comerciales`, `/vuelos/carga`, `/ruta_vuelo/<icao24>` endpoints.
- `collector.py` — a simple background collector that periodically requests OpenSky and upserts latest per-aircraft data into MongoDB `flights` collection.
- `data/operator_mapping.json` — small operator prefix mapping used by the classifier.
- `tests/test_classify.py` — unit tests for the classifier.
- `start_server.ps1` and `start_collector.ps1` — small convenience scripts to run the server and collector in PowerShell.

Environment variables (recommended)
- OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET — OpenSky OAuth client credentials. If not set, the defaults in the code will be used (development only).
- MONGODB_URI — mongodb connection string (e.g. `mongodb+srv://user:pass@cluster0/...`). If set and `pymongo` is installed, the app and collector will persist flights.
- ZABBIX_API, ZABBIX_USER, ZABBIX_PASS — optional, to enable the placeholder Zabbix login/metrics flow.
- COLLECT_INTERVAL — seconds between collector polls (default 15).

Run locally (PowerShell)
1) (Optional) Create a venv and install requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) Run the Flask server (dev):

```powershell
# Set env vars if desired and run server
$env:OPENSKY_CLIENT_ID = "your_id"
$env:OPENSKY_CLIENT_SECRET = "your_secret"
# optional: $env:MONGODB_URI = "your_mongo_uri"
.\start_server.ps1
```

3) Start collector (in another terminal) if you want persistent records in MongoDB:

```powershell
# ensure MONGODB_URI is set if you want persistence
.\start_collector.ps1
```

Run tests

```powershell
python -m unittest discover -v tests
```

Notes and next steps
- Classification is heuristic. For production, use an operator database or cross-reference aircraft registration/type.
- The frontend polls every 3s which may be aggressive; consider increasing to reduce API rate usage.
- Zabbix support is a placeholder. If you want full integration, provide host/item IDs and desired metrics and I will implement the push.
- Consider adding Docker files or systemd service files for production-run of collector and app.

If you'd like, I can now:
- Start the Flask server in a terminal and show live output.
- Start the collector (requires `MONGODB_URI` to persist).
- Extend Zabbix integration to send real metrics.
- Add a small operator CSV mapping and more tests.
