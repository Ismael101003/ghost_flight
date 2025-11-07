#!/usr/bin/env python3

import time
import signal
import sys
import logging
from typing import Optional
from app import obtener_token, classify_flight, MONGODB_URI

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

import requests
import os

# Configuración del logger en español
logger = logging.getLogger("colector")
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')

# Variables globales
RUNNING = True
INTERVALO = int(os.environ.get("COLLECT_INTERVAL", "15"))  # segundos

# Límites geográficos aproximados (México y alrededores)
LAT_MIN = 14.0
LAT_MAX = 33.0
LON_MIN = -118.0
LON_MAX = -86.0

# Conexión con MongoDB
cliente = None
db = None
if MONGODB_URI and MongoClient is not None:
    try:
        cliente = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        cliente.server_info()
        db = cliente.get_default_database()
        logger.info("✅ Conectado a MongoDB correctamente.")
    except Exception as e:
        logger.warning(f"⚠️ No se pudo conectar a MongoDB: {e}")
        cliente = None
        db = None
else:
    if MONGODB_URI and MongoClient is None:
        logger.warning("⚠️ pymongo no está instalado; el colector no podrá guardar datos.")


def apagar(signum, frame):
    global RUNNING
    logger.info("🛑 Deteniendo el colector...")
    RUNNING = False


signal.signal(signal.SIGINT, apagar)
signal.signal(signal.SIGTERM, apagar)


def obtener_estados():
    """Obtiene los datos de vuelos desde OpenSky API."""
    token = obtener_token()
    url = "https://opensky-network.org/api/states/all"
    params = {
        "lamin": LAT_MIN,
        "lomin": LON_MIN,
        "lamax": LAT_MAX,
        "lomax": LON_MAX,
    }
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Colector/1.0"}
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def procesar_y_guardar(estados_json: dict):
    """Procesa los datos de los vuelos y los guarda en MongoDB."""
    marca_tiempo = int(time.time())
    estados = estados_json.get("states", [])
    for estado in estados:
        icao24 = estado[0]
        callsign = estado[1].strip() if estado[1] else ""
        lat = estado[6]
        lon = estado[5]
        if lat is None or lon is None:
            continue
        tipo = classify_flight(callsign)
        doc = {
            "icao24": icao24,
            "callsign": callsign if callsign else "N/A",
            "pais_origen": estado[2],
            "latitud": lat,
            "longitud": lon,
            "altitud": estado[7],
            "velocidad": estado[9],
            "direccion": estado[10],
            "tipo": tipo,
            "fecha_captura": marca_tiempo,
        }
        if db is not None:
            try:
                coleccion = db.get_collection("flights")
                coleccion.update_one(
                    {"icao24": icao24},
                    {"$set": doc, "$currentDate": {"ultima_actualizacion": True}},
                    upsert=True
                )
            except Exception as e:
                logger.warning(f"⚠️ Error al escribir en la base de datos para {icao24}: {e}")


def main():
    logger.info(f"🚀 Iniciando colector (intervalo = {INTERVALO}s)")
    global RUNNING
    while RUNNING:
        try:
            datos = obtener_estados()
            procesar_y_guardar(datos)
        except requests.HTTPError as e:
            logger.error(f"❌ Error HTTP al obtener los estados: {e}")
        except Exception as e:
            logger.exception(f"💥 Error inesperado en el ciclo del colector: {e}")
        # Esperar el siguiente ciclo
        dormido = 0
        while RUNNING and dormido < INTERVALO:
            time.sleep(1)
            dormido += 1

    logger.info("✅ Colector detenido correctamente.")


if __name__ == '__main__':
    main()
