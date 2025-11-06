import requests
import time
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError


MONGO_URI = "mongodb+srv://ghost_flight_user:<TU_PASSWORD_AQUI>@ghost-flight-cluster.xxxxx.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "ghost_flight_db"
COLLECTION_NAME = "vuelos"


[cite_start]# [cite: 28-32]
OPENSKY_URL = "https://opensky-network.org/api/states/all"
OPENSKY_PARAMS = {
    [cite_start]"lamin": 18.5,  
    [cite_start]"lamax": 20.5,  
    [cite_start]"lomin": -100.0, 
    [cite_start]"lomax": -98.5   
}

def connect_to_db():
    """Conecta a Mongo Atlas y devuelve el objeto de la colección."""
    try:
        print(f"Conectando a MongoDB Atlas...")
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
        print("¡Conexión exitosa a MongoDB!")
        return collection
    except ConnectionFailure as e:
        print(f"Error de conexión a MongoDB: {e}")
        return None
    except Exception as e:
        print(f"Error desconocido al conectar a DB: {e}")
        return None

def fetch_and_store_flights(collection):
    """Obtiene datos de OpenSky y los guarda en MongoDB."""
    try:
        
        print("Consultando API de OpenSky...")
        res = requests.get(OPENSKY_URL, params=OPENSKY_PARAMS)
        res.raise_for_status() 
        data = res.json()

        if not data['states']:
            print("No se encontraron vuelos en el área.")
            return

       
        collection.delete_many({})

        vuelos_para_insertar = []
        for state in data['states']:
            
            callsign_limpio = state[1].strip()
            
            
            if not callsign_limpio or not state[2]:
                continue

            vuelo = {
                "icao24": state[0],
                "callsign": callsign_limpio,
                "origin_country": state[2],
                "time_position": state[3],
                "last_contact": state[4],
                "longitude": state[5],
                "latitude": state[6],
                "baro_altitude": state[7],
                "on_ground": state[8],
                "velocity": state[9],
                "true_track": state[10], # ¡Para rotar el icono!
                "vertical_rate": state[11],
                "sensors": state[12],
                "geo_altitude": state[13],
                "squawk": state[14],
                "spi": state[15],
                "position_source": state[16]
            }
            vuelos_para_insertar.append(vuelo)

        # [cite_start]2. Almacenar esos datos en la base de datos [cite: 9]
        if vuelos_para_insertar:
            collection.insert_many(vuelos_para_insertar)
            print(f"¡Éxito! {len(vuelos_para_insertar)} vuelos guardados en la base de datos.")

    except requests.exceptions.RequestException as e:
        print(f"Error al llamar a la API de OpenSky: {e}")
    except PyMongoError as e:
        print(f"Error al escribir en MongoDB: {e}")
    except Exception as e:
        print(f"Error inesperado en fetch_and_store_flights: {e}")


# --- Bucle Principal ---
if __name__ == "__main__":
    vuelos_collection = connect_to_db()
    
    if vuelos_collection is not None:
        while True:
            fetch_and_store_flights(vuelos_collection)
            print("Durmiendo por 60 segundos...")
            time.sleep(60)