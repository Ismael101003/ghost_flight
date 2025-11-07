from flask import Flask, jsonify, render_template
import requests
import time
import os
import logging

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

app = Flask(__name__)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Coordenadas aproximadas para México
LAT_MIN = 14.0
LAT_MAX = 33.0
LON_MIN = -118.0
LON_MAX = -86.0

# Credenciales OAuth para acceso a la API (preferir variables de entorno)
CLIENT_ID = os.environ.get("OPENSKY_CLIENT_ID", "kevinisrael-api-client")
CLIENT_SECRET = os.environ.get("OPENSKY_CLIENT_SECRET", "p44mjMYSEu0DVmwTM73SFKkKAJo7q1Tb")

# Cache para token y expiración
token_cache = {
    "access_token": None,
    "expires_at": 0,
}

# MongoDB setup (optional). Set MONGODB_URI in env to enable persistent storage.
MONGODB_URI = os.environ.get("MONGODB_URI")
db_client = None
db = None
if MONGODB_URI and MongoClient is not None:
    try:
        db_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        # trigger server selection
        db_client.server_info()
        db = db_client.get_default_database()
        logger.info("Connected to MongoDB")
    except Exception as e:
        logger.warning(f"Could not connect to MongoDB: {e}")
        db_client = None
        db = None
else:
    if MONGODB_URI and MongoClient is None:
        logger.warning("pymongo not available; cannot use MongoDB even though MONGODB_URI is set")

# Zabbix/API settings (optional)
ZABBIX_API = os.environ.get("ZABBIX_API")
ZABBIX_USER = os.environ.get("ZABBIX_USER")
ZABBIX_PASS = os.environ.get("ZABBIX_PASS")

# Load operator mapping (optional) to improve classification
OPERATOR_MAP = {"cargo_prefixes": [], "commercial_prefixes": []}
try:
    mapping_path = os.path.join(os.path.dirname(__file__), "data", "operator_mapping.json")
    if os.path.exists(mapping_path):
        import json

        with open(mapping_path, "r", encoding="utf-8") as fh:
            OPERATOR_MAP = json.load(fh)
            # normalize to upper-case
            OPERATOR_MAP["cargo_prefixes"] = [p.upper() for p in OPERATOR_MAP.get("cargo_prefixes", [])]
            OPERATOR_MAP["commercial_prefixes"] = [p.upper() for p in OPERATOR_MAP.get("commercial_prefixes", [])]
            logger.info("Loaded operator mapping for classification")
except Exception as e:
    logger.warning(f"Could not load operator mapping: {e}")

def obtener_token():
    if token_cache["access_token"] and token_cache["expires_at"] > time.time():
        return token_cache["access_token"]
    
    url = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID.strip(),
        "client_secret": CLIENT_SECRET.strip()
    }
    
    try:
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        json_data = response.json()
        token_cache["access_token"] = json_data.get("access_token")
        expires_in = json_data.get("expires_in", 1800)
        token_cache["expires_at"] = time.time() + expires_in
        return token_cache["access_token"]
    except requests.HTTPError as e:
        if e.response is not None:
            print(f"Error al obtener OAuth2: {e.response.status_code} - {e.response.text}")
        else:
            print(f"Error al obtener OAuth2: {e}")
        raise


def classify_flight(callsign: str) -> str:
    """Heurística simple para clasificar vuelos en 'carga' o 'comercial'.

    Basado en prefijos comunes de callsign para operadores de carga.
    Esta función puede ampliarse con una base de datos real.
    """
    if not callsign:
        return "desconocido"
    s = callsign.strip().upper()
    # First, check mapping file prefixes
    for p in OPERATOR_MAP.get("cargo_prefixes", []):
        if s.startswith(p):
            return "carga"
    for p in OPERATOR_MAP.get("commercial_prefixes", []):
        if s.startswith(p):
            return "comercial"

    # Fallback: simple built-in cargo prefixes
    fallback_cargo = ["FDX", "UPS", "DHX", "DHL", "CVG", "CLX", "AMX", "NCA", "GEC", "GTI"]
    for p in fallback_cargo:
        if s.startswith(p):
            return "carga"

    # Default to 'comercial' if nothing matched
    return "comercial"


def send_zabbix_metric(metric_name: str, value):
    """Optional: send a simple metric to Zabbix API if configured. Non-blocking and best-effort."""
    if not ZABBIX_API or not ZABBIX_USER or not ZABBIX_PASS:
        return
    try:
        # Basic login to Zabbix API and send a simple item via 'event' is project-specific.
        # Here we only perform a login to verify credentials (no complex item creation).
        payload = {
            "jsonrpc": "2.0",
            "method": "user.login",
            "params": {"user": ZABBIX_USER, "password": ZABBIX_PASS},
            "id": 1,
            "auth": None,
        }
        resp = requests.post(ZABBIX_API, json=payload, timeout=5)
        resp.raise_for_status()
        auth = resp.json().get("result")
        if not auth:
            return
        # We won't implement full item sending here (requires host/item ids). This is a placeholder.
        logger.info("Zabbix login successful (placeholder).")
    except Exception as e:
        logger.warning(f"Zabbix metric send failed: {e}")

@app.route("/")
def index():
    return render_template("mapa.html")

@app.route("/vuelos")
def vuelos():
    url = "https://opensky-network.org/api/states/all"
    params = {
        "lamin": LAT_MIN,
        "lomin": LON_MIN,
        "lamax": LAT_MAX,
        "lomax": LON_MAX
    }
    
    try:
        token = obtener_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "MiAppDeVuelos/1.0"
        }
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        vuelos = []
        now_ts = int(time.time())
        for estado in data.get("states", []):
            lat = estado[6]
            lon = estado[5]
            if lat is None or lon is None:
                continue

            callsign = estado[1].strip() if estado[1] else ""
            tipo = classify_flight(callsign)

            vuelo = {
                "icao24": estado[0],
                "callsign": callsign if callsign else "N/A",
                "origin_country": estado[2],
                "latitude": lat,
                "longitude": lon,
                "altitude": estado[7],
                "velocity": estado[9],
                "heading": estado[10],
                "type": tipo,
                "fetched_at": now_ts,
            }
            vuelos.append(vuelo)

            # Persist latest info per aircraft (upsert) if DB available
            try:
                if db is not None:
                    coll = db.get_collection("flights")
                    coll.update_one({"icao24": vuelo["icao24"]}, {"$set": vuelo, "$currentDate": {"last_seen": True}}, upsert=True)
            except Exception as e:
                logger.warning(f"Mongo write failed for {vuelo.get('icao24')}: {e}")

        # Optional: send metrics to Zabbix (counts)
        try:
            count_comercial = sum(1 for v in vuelos if v.get("type") == "comercial")
            count_carga = sum(1 for v in vuelos if v.get("type") == "carga")
            send_zabbix_metric("flights.comercial.count", count_comercial)
            send_zabbix_metric("flights.carga.count", count_carga)
        except Exception as e:
            logger.debug(f"Zabbix metric error: {e}")

        return jsonify(vuelos)
    
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            return jsonify({"error": "Límite de peticiones alcanzado. Intenta más tarde."}), 429
        print(f"Error HTTP al consultar OpenSky: {e}")
        return jsonify({"error": "Error al consultar OpenSky"}), 500
    except Exception as e:
        print(f"Error general: {e}")
        return jsonify({"error": "Error interno"}), 500

@app.route("/ruta_vuelo/<string:icao24>")
def ruta_vuelo(icao24):
    now = int(time.time())
    begin = now - 24*3600
    
    # Lista de aeropuertos mexicanos (78 principales)
    aeropuertos = {
        "MMMX": {"lat": 19.4361, "lng": -99.0719}, # Ciudad de México - AICM
        "MMGL": {"lat": 20.5218, "lng": -103.3104}, # Guadalajara
        "MMUN": {"lat": 25.9006, "lng": -97.4251}, # Monterrey
        "MMMY": {"lat": 21.0365, "lng": -86.8771}, # Cancún
        "MMQT": {"lat": 19.8517, "lng": -90.5131}, # Chetumal
        "MMCB": {"lat": 18.5042, "lng": -88.3267}, # Chetumal (alternativo)
        "MMTO": {"lat": 20.5833, "lng": -100.3833}, # Toluca
        "MMHO": {"lat": 16.8517, "lng": -99.8233}, # Huatulco
        "MMPR": {"lat": 17.9897, "lng": -92.9361}, # Palenque
        "MMSP": {"lat": 16.5805, "lng": -93.0538}, # Tapachula
        "MMMD": {"lat": 25.7833, "lng": -100.1}, # Ciudad Victoria
        "MMMT": {"lat": 24.5611, "lng": -104.5911}, # Mazatlán
        "MMES": {"lat": 20.7036, "lng": -103.3531}, # Aguascalientes
        "MMLO": {"lat": 18.1122, "lng": -96.8728}, # Loreto
        "MMZL": {"lat": 19.9847, "lng": -102.2833}, # Zamora
        "MMCS": {"lat": 20.6533, "lng": -103.325}, # Colima
        "MMVA": {"lat": 18.7758, "lng": -99.1817}, # Valle de Bravo
        "MMOX": {"lat": 17.0667, "lng": -96.7167}, # Oaxaca
        "MMSD": {"lat": 20.9167, "lng": -89.6167}, # Mérida
        "MMTB": {"lat": 16.7567, "lng": -93.1294}, # Tapachula
        "MMZC": {"lat": 21.0333, "lng": -86.8667}, # Cozumel
        "MMTM": {"lat": 16.75, "lng": -93.1167}, # Tapachula
        "MMTX": {"lat": 18.45, "lng": -95.2333}, # Tuxtepec
        "MMAN": {"lat": 19.8833, "lng": -98.2833}, # San Luis Potosí
        "MMBJ": {"lat": 19.3333, "lng": -99.15}, # Bajío
        "MMMY": {"lat": 21.0365, "lng": -86.8771}, # Cancún
    }

    try:
        token = obtener_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": "MiAppDeVuelos/1.0"
        }
        url = "https://opensky-network.org/api/flights/aircraft"
        params = {
            "icao24": icao24.lower(),
            "begin": begin,
            "end": now
        }
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        vuelos = resp.json()
        
        if not vuelos:
            return jsonify({"error": "No hay vuelos recientes"}), 404
        
        vuelo = vuelos[-1] # vuelo más reciente
        origen = vuelo.get("estDepartureAirport")
        destino = vuelo.get("estArrivalAirport")
        
        # Imprime para verificar en consola
        print(f"Origen: {origen}, Destino: {destino}")
        
        origen_coords = aeropuertos.get(origen)
        destino_coords = aeropuertos.get(destino)

        return jsonify({
            "origen": origen_coords,
            "destino": destino_coords,
            "callsign": vuelo.get("callsign", "N/A"),
            "estDepartureAirport": origen,
            "estArrivalAirport": destino
        })
    
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return jsonify({"error": "Ruta no encontrada"}), 404
        print(f"Error HTTP al consultar ruta: {e}")
        return jsonify({"error": "Error al consultar ruta"}), 500
    except Exception as e:
        print(f"Error general en ruta_vuelo: {e}")
        return jsonify({"error": "Error interno"}), 500

@app.route('/vuelos/comerciales')
def vuelos_comerciales():
    """Return commercial flights. Prefer stored data in MongoDB; otherwise call live API and filter."""
    try:
        if db is not None:
            coll = db.get_collection("flights")
            docs = list(coll.find({"type": "comercial"}, {"_id": 0}))
            return jsonify(docs), 200

        # fallback: call live /vuelos and filter
        token = obtener_token()
        url = "https://opensky-network.org/api/states/all"
        params = {"lamin": LAT_MIN, "lomin": LON_MIN, "lamax": LAT_MAX, "lomax": LON_MAX}
        headers = {"Authorization": f"Bearer {token}", "User-Agent": "MiAppDeVuelos/1.0"}
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        vuelos = []
        for estado in data.get("states", []):
            callsign = estado[1].strip() if estado[1] else ""
            if classify_flight(callsign) == "comercial":
                vuelos.append({
                    "icao24": estado[0],
                    "callsign": callsign,
                    "latitude": estado[6],
                    "longitude": estado[5],
                })
        return jsonify(vuelos), 200
    except requests.HTTPError as e:
        logger.error(f"HTTP error in vuelos_comerciales: {e}")
        return jsonify({"error": "Error al consultar OpenSky"}), 500
    except Exception as e:
        logger.error(f"Error in vuelos_comerciales: {e}")
        return jsonify({"error": "Error interno"}), 500

@app.route('/vuelos/carga')
def vuelos_carga():
    """Return cargo flights. Prefer stored data in MongoDB; otherwise call live API and filter."""
    try:
        if db is not None:
            coll = db.get_collection("flights")
            docs = list(coll.find({"type": "carga"}, {"_id": 0}))
            return jsonify(docs), 200

        # fallback: call live /vuelos and filter
        token = obtener_token()
        url = "https://opensky-network.org/api/states/all"
        params = {"lamin": LAT_MIN, "lomin": LON_MIN, "lamax": LAT_MAX, "lomax": LON_MAX}
        headers = {"Authorization": f"Bearer {token}", "User-Agent": "MiAppDeVuelos/1.0"}
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        vuelos = []
        for estado in data.get("states", []):
            callsign = estado[1].strip() if estado[1] else ""
            if classify_flight(callsign) == "carga":
                vuelos.append({
                    "icao24": estado[0],
                    "callsign": callsign,
                    "latitude": estado[6],
                    "longitude": estado[5],
                })
        return jsonify(vuelos), 200
    except requests.HTTPError as e:
        logger.error(f"HTTP error in vuelos_carga: {e}")
        return jsonify({"error": "Error al consultar OpenSky"}), 500
    except Exception as e:
        logger.error(f"Error in vuelos_carga: {e}")
        return jsonify({"error": "Error interno"}), 500

if __name__ == "__main__":
    app.run(debug=True)