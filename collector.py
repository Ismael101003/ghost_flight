#!/usr/bin/env python3
"""
Simple collector that periodically queries OpenSky states for the Mexico bbox
and upserts latest state per `icao24` into MongoDB (collection `flights`).

It reuses the token and classification logic from `app.py`.
"""
import time
import signal
import sys
import logging
from typing import Optional

# Import helpers from app (token, classify_flight, and DB config)
from app import obtener_token, classify_flight, MONGODB_URI

try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

import requests
import os

logger = logging.getLogger("collector")
logging.basicConfig(level=logging.INFO)

RUNNING = True
INTERVAL = int(os.environ.get("COLLECT_INTERVAL", "15"))  # seconds

LAT_MIN = 14.0
LAT_MAX = 33.0
LON_MIN = -118.0
LON_MAX = -86.0

client = None
db = None
if MONGODB_URI and MongoClient is not None:
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        client.server_info()
        db = client.get_default_database()
        logger.info("Collector connected to MongoDB")
    except Exception as e:
        logger.warning(f"Collector could not connect to MongoDB: {e}")
        client = None
        db = None
else:
    if MONGODB_URI and MongoClient is None:
        logger.warning("pymongo not installed; collector cannot persist to DB")


def shutdown(signum, frame):
    global RUNNING
    logger.info("Shutting down collector")
    RUNNING = False


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)


def fetch_states():
    token = obtener_token()
    url = "https://opensky-network.org/api/states/all"
    params = {
        "lamin": LAT_MIN,
        "lomin": LON_MIN,
        "lamax": LAT_MAX,
        "lomax": LON_MAX,
    }
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "Collector/1.0"}
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def process_and_store(states_json: dict):
    now_ts = int(time.time())
    states = states_json.get("states", [])
    for estado in states:
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
            "origin_country": estado[2],
            "latitude": lat,
            "longitude": lon,
            "altitude": estado[7],
            "velocity": estado[9],
            "heading": estado[10],
            "type": tipo,
            "fetched_at": now_ts,
        }
        if db is not None:
            try:
                coll = db.get_collection("flights")
                coll.update_one({"icao24": icao24}, {"$set": doc, "$currentDate": {"last_seen": True}}, upsert=True)
            except Exception as e:
                logger.warning(f"DB write failed for {icao24}: {e}")


def main():
    logger.info(f"Starting collector (interval={INTERVAL}s)")
    global RUNNING
    while RUNNING:
        try:
            data = fetch_states()
            process_and_store(data)
        except requests.HTTPError as e:
            logger.error(f"HTTP error fetching states: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error in collector loop: {e}")
        # Sleep but respond to shutdown quickly
        slept = 0
        while RUNNING and slept < INTERVAL:
            time.sleep(1)
            slept += 1

    logger.info("Collector stopped")


if __name__ == '__main__':
    main()
