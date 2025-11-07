from flask import Flask, jsonify, render_template
import requests
import time
import os
import logging
import json
from dotenv import load_dotenv

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

from gemini_service import GeminiService
from elevenlabs_service import ElevenLabsService

load_dotenv()

app = Flask(__name__)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Coordenadas aproximadas para CDMX área
LAT_MIN = 19.0
LAT_MAX = 20.2
LON_MIN = -99.5
LON_MAX = -98.8

# Credenciales OAuth para acceso a la API (preferir variables de entorno)
CLIENT_ID = os.environ.get("OPENSKY_CLIENT_ID", "pop-api-client")
CLIENT_SECRET = os.environ.get("OPENSKY_CLIENT_SECRET", "nBLFkW00mznAUsbmcJvEgAr88msF82WT")

# Cache para token y expiración
token_cache = {
    "access_token": None,
    "expires_at": 0,
}

alerts_history = []
alerts_config = {
    "cargo_entry_enabled": True,
    "high_count_enabled": True,
    "high_count_threshold": 10,
    "low_altitude_enabled": True,
    "low_altitude_threshold": 3000,
    "abnormal_speed_enabled": True,
    "abnormal_speed_threshold": 500,
    "sound_enabled": True
}

# MongoDB setup (optional). Set MONGODB_URI in env to enable persistent storage.
MONGODB_URI = os.environ.get("MONGODB_URI")
db_client = None
db = None
if MONGODB_URI and MongoClient is not None:
    try:
        db_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        db_client.server_info()  # Test connection
        db = db_client.get_default_database()
        logger.info("✅ Conectado a MongoDB para app.py.")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo conectar a MongoDB: {e}")
        db_client = None
        db = None
else:
    if MONGODB_URI and MongoClient is None:
        logger.warning("⚠️ pymongo no está instalado.")

# Zabbix/API settings (optional)
ZABBIX_API = os.environ.get("ZABBIX_API")
ZABBIX_USER = os.environ.get("ZABBIX_USER")
ZABBIX_PASS = os.environ.get("ZABBIX_PASS")

# Load operator mapping (optional) to improve classification
OPERATOR_MAP = {"cargo_prefixes": [], "commercial_prefixes": []}
try:
    mapping_path = os.path.join(os.path.dirname(__file__), "data", "operator_mapping.json")
    if os.path.exists(mapping_path):
        with open(mapping_path, "r", encoding="utf-8") as fh:
            OPERATOR_MAP = json.load(fh)
            # normalize to upper-case
            OPERATOR_MAP["cargo_prefixes"] = [p.upper() for p in OPERATOR_MAP.get("cargo_prefixes", [])]
            OPERATOR_MAP["commercial_prefixes"] = [p.upper() for p in OPERATOR_MAP.get("commercial_prefixes", [])]
            logger.info("Loaded operator mapping for classification")
except Exception as e:
    logger.warning(f"Could not load operator mapping: {e}")

seen_cargo_flights = set()

gemini_service = GeminiService()
elevenlabs_service = ElevenLabsService()

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

def check_alerts(vuelos):
    """Check flight data against alert rules and generate alerts"""
    new_alerts = []
    
    # Count cargo and total flights
    count_cargo = sum(1 for v in vuelos if v.get("type") == "carga")
    count_total = len(vuelos)
    
    # Alert: New cargo flight entry
    if alerts_config["cargo_entry_enabled"]:
        for vuelo in vuelos:
            if vuelo.get("type") == "carga" and vuelo.get("icao24") not in seen_cargo_flights:
                seen_cargo_flights.add(vuelo.get("icao24"))
                alert = {
                    "id": int(time.time() * 1000),
                    "type": "cargo_entry",
                    "title": "Vuelo de Carga Detectado",
                    "message": f"Nuevo vuelo de carga {vuelo.get('callsign', 'N/A')} ha entrado en el área",
                    "severity": "warning",
                    "timestamp": int(time.time()),
                    "flight_data": {
                        "callsign": vuelo.get("callsign"),
                        "icao24": vuelo.get("icao24"),
                        "altitude": vuelo.get("altitude")
                    }
                }
                new_alerts.append(alert)
    
    # Alert: High count of flights
    if alerts_config["high_count_enabled"] and count_total > alerts_config["high_count_threshold"]:
        alert = {
            "id": int(time.time() * 1000) + 1,
            "type": "high_count",
            "title": "Alto Tráfico Aéreo",
            "message": f"Se detectaron {count_total} vuelos en el área (umbral: {alerts_config['high_count_threshold']})",
            "severity": "info",
            "timestamp": int(time.time()),
            "flight_data": {
                "total": count_total,
                "cargo": count_cargo
            }
        }
        # Only add if not recently added
        if not any(a.get("type") == "high_count" for a in alerts_history[-5:]):
            new_alerts.append(alert)
    
    # Alert: Low altitude flights
    if alerts_config["low_altitude_enabled"]:
        for vuelo in vuelos:
            if vuelo.get("altitude") and vuelo.get("altitude") < alerts_config["low_altitude_threshold"]:
                alert = {
                    "id": int(time.time() * 1000) + 2,
                    "type": "low_altitude",
                    "title": "Altitud Baja Detectada",
                    "message": f"Vuelo {vuelo.get('callsign', 'N/A')} a {vuelo.get('altitude')} ft (umbral: {alerts_config['low_altitude_threshold']} ft)",
                    "severity": "danger",
                    "timestamp": int(time.time()),
                    "flight_data": {
                        "callsign": vuelo.get("callsign"),
                        "icao24": vuelo.get("icao24"),
                        "altitude": vuelo.get("altitude")
                    }
                }
                # Only add if not recently added for this flight
                if not any(a.get("flight_data", {}).get("icao24") == vuelo.get("icao24") and a.get("type") == "low_altitude" for a in alerts_history[-10:]):
                    new_alerts.append(alert)
    
    # Alert: Abnormal speed
    if alerts_config["abnormal_speed_enabled"]:
        for vuelo in vuelos:
            if vuelo.get("velocity") and vuelo.get("velocity") > alerts_config["abnormal_speed_threshold"]:
                alert = {
                    "id": int(time.time() * 1000) + 3,
                    "type": "abnormal_speed",
                    "title": "Velocidad Anormal",
                    "message": f"Vuelo {vuelo.get('callsign', 'N/A')} a {vuelo.get('velocity')} knots (umbral: {alerts_config['abnormal_speed_threshold']} knots)",
                    "severity": "warning",
                    "timestamp": int(time.time()),
                    "flight_data": {
                        "callsign": vuelo.get("callsign"),
                        "icao24": vuelo.get("icao24"),
                        "velocity": vuelo.get("velocity")
                    }
                }
                if not any(a.get("flight_data", {}).get("icao24") == vuelo.get("icao24") and a.get("type") == "abnormal_speed" for a in alerts_history[-10:]):
                    new_alerts.append(alert)
    
    # Add new alerts to history
    alerts_history.extend(new_alerts)
    
    # Keep only last 100 alerts
    if len(alerts_history) > 100:
        del alerts_history[:-100]
    
    return new_alerts


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
                if db and db_client:
                    db.get_collection("flights").update_one({"icao24": estado[0]}, {"$set": vuelo}, upsert=True)
            except Exception as e:
                logger.warning(f"Mongo write failed for {vuelo.get('icao24')}: {e}")

        check_alerts(vuelos)

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

@app.route("/alerts")
def get_alerts():
    """Return recent alerts"""
    return jsonify(alerts_history[-20:]), 200

@app.route("/alerts/config")
def get_alerts_config():
    """Return current alert configuration"""
    return jsonify(alerts_config), 200

@app.route("/alerts/config", methods=["POST"])
def update_alerts_config():
    """Update alert configuration"""
    from flask import request
    try:
        new_config = request.get_json()
        if new_config:
            alerts_config.update(new_config)
            return jsonify({"success": True, "config": alerts_config}), 200
        return jsonify({"error": "No data provided"}), 400
    except Exception as e:
        logger.error(f"Error updating alerts config: {e}")
        return jsonify({"error": "Error updating configuration"}), 500

@app.route("/alerts/clear", methods=["POST"])
def clear_alerts():
    """Clear alerts history"""
    alerts_history.clear()
    seen_cargo_flights.clear()
    return jsonify({"success": True}), 200

@app.route("/alerts/export")
def export_alerts():
    """Export alerts to JSON"""
    from flask import Response
    json_data = json.dumps(alerts_history, indent=2)
    return Response(
        json_data,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment;filename=alerts_export_{int(time.time())}.json"}
    )

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
        
        # Obtener el estado actual del vuelo de MongoDB (o simular)
        current_flight_state = {}
        if db is not None:
            current_flight_state = db.get_collection("flights").find_one({"icao24": icao24}) or {}
        
        # Imprime para verificar en consola
        print(f"Origen: {origen}, Destino: {destino}")
        
        origen_coords = aeropuertos.get(origen)
        destino_coords = aeropuertos.get(destino)

        analysis = None
        audio_url = None
        
        # 1. Llamar a Gemini con los datos combinados
        if gemini_service.is_available():
            flight_data_for_gemini = {
                "callsign": vuelo.get("callsign", "N/A"),
                "type": classify_flight(vuelo.get("callsign", "")),
                "origin_country": current_flight_state.get("pais_origen") or current_flight_state.get("origin_country"),
                "altitude": current_flight_state.get("altitud") or current_flight_state.get("altitude"),
                "velocity": current_flight_state.get("velocidad") or current_flight_state.get("velocity"),
                "heading": current_flight_state.get("direccion") or current_flight_state.get("heading"),
                "departure": origen,
                "arrival": destino,
            }
            
            analysis = gemini_service.analyze_flight_pattern(flight_data_for_gemini)
            
            # 2. Llamar a ElevenLabs si el análisis fue exitoso
            if analysis and elevenlabs_service.is_available():
                audio_data = elevenlabs_service.generate_alert_audio(analysis, alert_type="info")
                
                # Guardar el audio y generar la URL pública
                if audio_data:
                    static_dir = os.path.join(app.root_path, 'static')
                    os.makedirs(static_dir, exist_ok=True)
                    audio_filename = f"analysis_{icao24}.mp3"
                    audio_filepath = os.path.join(static_dir, audio_filename)
                    
                    with open(audio_filepath, 'wb') as f:
                        f.write(audio_data)
                        
                    audio_url = f"/static/{audio_filename}"

        return jsonify({
            "origen": origen_coords,
            "destino": destino_coords,
            "callsign": vuelo.get("callsign", "N/A"),
            "estDepartureAirport": origen,
            "estArrivalAirport": destino,
            "gemini_analysis": analysis,
            "audio_url": audio_url
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
        if db and db_client:
            docs = db.get_collection("flights").find({"type": "comercial"})
            return jsonify(list(docs)), 200

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
        if db and db_client:
            docs = db.get_collection("flights").find({"type": "carga"})
            return jsonify(list(docs)), 200

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

@app.route("/analyze/flight/<string:icao24>")
def analyze_flight(icao24):
    """Analiza un vuelo específico usando Gemini AI"""
    try:
        if not gemini_service.is_available():
            return jsonify({"error": "Servicio de análisis no disponible. Configura GEMINI_API_KEY."}), 503
        
        # Buscar el vuelo en los datos actuales
        if db and db_client:
            flight = db.get_collection("flights").find_one({"icao24": icao24})
        else:
            return jsonify({"error": "Base de datos no disponible"}), 503
        
        if not flight:
            return jsonify({"error": "Vuelo no encontrado"}), 404
        
        analysis = gemini_service.analyze_flight_pattern(flight)
        
        if analysis:
            return jsonify({
                "flight": flight,
                "analysis": analysis,
                "timestamp": int(time.time())
            }), 200
        else:
            return jsonify({"error": "Error al analizar el vuelo"}), 500
            
    except Exception as e:
        logger.error(f"Error en analyze_flight: {e}")
        return jsonify({"error": "Error interno"}), 500

@app.route("/analyze/traffic")
def analyze_traffic():
    """Analiza patrones de tráfico actual usando Gemini AI"""
    try:
        if not gemini_service.is_available():
            return jsonify({"error": "Servicio de análisis no disponible. Configura GEMINI_API_KEY."}), 503
        
        # Obtener vuelos actuales
        if db and db_client:
            flights = list(db.get_collection("flights").find())
        else:
            # Fallback: llamar al endpoint de vuelos
            return jsonify({"error": "Base de datos no disponible"}), 503
        
        stats = {
            "total": len(flights),
            "cargo": sum(1 for f in flights if f.get('type') == 'carga'),
            "commercial": sum(1 for f in flights if f.get('type') == 'comercial')
        }
        
        analysis = gemini_service.analyze_traffic_pattern(flights, stats)
        
        if analysis:
            return jsonify({
                "stats": stats,
                "analysis": analysis,
                "timestamp": int(time.time())
            }), 200
        else:
            return jsonify({"error": "Error al analizar patrones"}), 500
            
    except Exception as e:
        logger.error(f"Error en analyze_traffic: {e}")
        return jsonify({"error": "Error interno"}), 500

@app.route("/chat", methods=["POST"])
def chat():
    """Chatbot para consultas sobre vuelos usando Gemini AI"""
    from flask import request
    
    try:
        if not gemini_service.is_available():
            return jsonify({"error": "Servicio de chat no disponible. Configura GEMINI_API_KEY."}), 503
        
        data = request.get_json()
        query = data.get('query', '')
        
        if not query:
            return jsonify({"error": "Consulta vacía"}), 400
        
        # Obtener contexto actual
        context = {}
        if db and db_client:
            flights = list(db.get_collection("flights").find())
            context = {
                "total_flights": len(flights),
                "commercial_flights": sum(1 for f in flights if f.get('type') == 'comercial'),
                "cargo_flights": sum(1 for f in flights if f.get('type') == 'carga'),
                "recent_alerts": len(alerts_history[-10:]),
                "last_update": time.strftime('%Y-%m-%d %H:%M:%S')
            }
        
        response = gemini_service.chat_query(query, context)
        
        return jsonify({
            "query": query,
            "response": response,
            "timestamp": int(time.time())
        }), 200
        
    except Exception as e:
        logger.error(f"Error en chat: {e}")
        return jsonify({"error": "Error interno"}), 500

@app.route("/analyze/predict", methods=['GET'])
def analyze_predict():
    """Análisis predictivo de patrones de tráfico usando datos históricos y Gemini"""
    try:
        if not gemini_service.is_available():
            return jsonify({
                "error": "Análisis predictivo no disponible. Gemini API no configurada.",
                "timestamp": int(time.time()),
                "data_points": 0
            }), 503
        
        # Obtener datos históricos de las últimas 24 horas
        if db and db_client:
            historical_data = list(db.get_collection("historical_data").find({"timestamp": {"$gte": now - 24*3600}}))
            data_points = len(historical_data)
        else:
            # Si no hay MongoDB, usar datos actuales con múltiples muestras
            historical_data = []
            data_points = 0
            logger.warning("MongoDB no disponible. Análisis predictivo limitado.")
        
        # Obtener datos actuales
        current_flights = obtener_vuelos()
        
        # Preparar análisis para Gemini
        analysis_prompt = f"""
Eres un experto en análisis de tráfico aéreo y predicción de patrones.

DATOS ACTUALES:
- Total de vuelos: {len(current_flights)}
- Vuelos comerciales: {sum(1 for f in current_flights if f.get('type') == 'comercial')}
- Vuelos de carga: {sum(1 for f in current_flights if f.get('type') == 'carga')}
- Hora actual: {time.strftime('%H:%M', time.localtime())}

DATOS HISTÓRICOS:
- Puntos de datos disponibles: {data_points}
"""

        if data_points > 0:
            # Análisis por hora
            hourly_stats = {}
            for record in historical_data:
                hour = time.strftime('%H', time.localtime(record['timestamp']))
                if hour not in hourly_stats:
                    hourly_stats[hour] = {'total': 0, 'cargo': 0, 'commercial': 0, 'count': 0}
                
                flights = record.get('flights', [])
                hourly_stats[hour]['total'] += len(flights)
                hourly_stats[hour]['cargo'] += sum(1 for f in flights if f.get('type') == 'carga')
                hourly_stats[hour]['commercial'] += sum(1 for f in flights if f.get('type') == 'comercial')
                hourly_stats[hour]['count'] += 1
            
            # Calcular promedios
            avg_by_hour = {}
            for hour, stats in hourly_stats.items():
                if stats['count'] > 0:
                    avg_by_hour[hour] = {
                        'avg_total': stats['total'] / stats['count'],
                        'avg_cargo': stats['cargo'] / stats['count'],
                        'avg_commercial': stats['commercial'] / stats['count']
                    }
            
            analysis_prompt += f"\n\nPATRONES HORARIOS (últimas 24h):\n"
            for hour in sorted(avg_by_hour.keys()):
                stats = avg_by_hour[hour]
                analysis_prompt += f"- {hour}:00 - Promedio: {stats['avg_total']:.1f} vuelos (Carga: {stats['avg_cargo']:.1f}, Comercial: {stats['avg_commercial']:.1f})\n"
            
            # Detectar horas pico
            peak_hours = sorted(avg_by_hour.items(), key=lambda x: x[1]['avg_total'], reverse=True)[:3]
            analysis_prompt += f"\n\nHORAS PICO DETECTADAS:\n"
            for hour, stats in peak_hours:
                analysis_prompt += f"- {hour}:00 con promedio de {stats['avg_total']:.1f} vuelos\n"
            
            # Tendencias de carga
            cargo_by_hour = [(hour, stats['avg_cargo']) for hour, stats in avg_by_hour.items()]
            cargo_trend = "creciente" if len(cargo_by_hour) > 1 and cargo_by_hour[-1][1] > cargo_by_hour[0][1] else "decreciente"
            analysis_prompt += f"\n\nTENDENCIA DE VUELOS DE CARGA: {cargo_trend}\n"
        
        analysis_prompt += """

TAREA:
Proporciona un análisis predictivo detallado que incluya:

1. PREDICCIÓN DE TRÁFICO (próximas horas):
   - ¿Se espera aumento o disminución del tráfico?
   - ¿Cuántos vuelos se anticipan aproximadamente?

2. HORARIOS PICO ESPERADOS:
   - ¿Cuáles serán las próximas horas de mayor tráfico?
   - Justifica basándote en los patrones históricos

3. TENDENCIAS DE CARGA:
   - ¿Cómo evolucionarán los vuelos de carga?
   - ¿Hay patrones específicos a considerar?

4. RECOMENDACIONES OPERATIVAS:
   - ¿Qué acciones se sugieren para el monitoreo?
   - ¿Hay algún patrón anómalo o preocupante?

5. NIVEL DE CONFIANZA:
   - Evalúa la confiabilidad de tu predicción (Alta/Media/Baja)
   - Justifica tu evaluación

Responde de manera clara, profesional y estructurada. Usa datos específicos cuando sea posible.
"""

        # Solicitar análisis a Gemini
        prediction = gemini_service.generate_response(analysis_prompt)
        
        return jsonify({
            "prediction": {
                "raw_analysis": prediction
            },
            "timestamp": int(time.time()),
            "data_points": data_points,
            "current_flights": len(current_flights),
            "has_historical_data": data_points > 0
        })
        
    except Exception as e:
        logger.error(f"Error en análisis predictivo: {e}")
        return jsonify({
            "error": str(e),
            "timestamp": int(time.time()),
            "data_points": 0
        }), 500

@app.route("/alerts/<int:alert_id>/audio")
def get_alert_audio(alert_id):
    """Genera y devuelve audio para una alerta específica"""
    from flask import Response
    
    try:
        if not elevenlabs_service.is_available():
            return jsonify({"error": "Servicio de voz no disponible. Configura ELEVENLABS_API_KEY."}), 503
        
        # Buscar la alerta
        alert = next((a for a in alerts_history if a.get('id') == alert_id), None)
        
        if not alert:
            return jsonify({"error": "Alerta no encontrada"}), 404
        
        # Crear narración
        narration = elevenlabs_service.create_alert_narration(alert)
        
        # Generar audio
        audio_data = elevenlabs_service.generate_alert_audio(
            narration, 
            alert.get('severity', 'info')
        )
        
        if audio_data:
            return Response(
                audio_data,
                mimetype="audio/mpeg",
                headers={"Content-Disposition": f"attachment;filename=alert_{alert_id}.mp3"}
            )
        else:
            return jsonify({"error": "Error al generar audio"}), 500
            
    except Exception as e:
        logger.error(f"Error en get_alert_audio: {e}")
        return jsonify({"error": "Error interno"}), 500

@app.route("/ai/status")
def ai_status():
    """Retorna el estado de los servicios de IA"""
    return jsonify({
        "gemini": {
            "available": gemini_service.is_available(),
            "configured": gemini_service.api_key is not None
        },
        "elevenlabs": {
            "available": elevenlabs_service.is_available(),
            "configured": elevenlabs_service.api_key is not None
        }
    }), 200

def obtener_vuelos():
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
        
        return vuelos
    
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            return jsonify({"error": "Límite de peticiones alcanzado. Intenta más tarde."}), 429
        print(f"Error HTTP al consultar OpenSky: {e}")
        return jsonify({"error": "Error al consultar OpenSky"}), 500
    except Exception as e:
        print(f"Error general: {e}")
        return jsonify({"error": "Error interno"}), 500

if __name__ == "__main__":
    app.run(debug=True)
