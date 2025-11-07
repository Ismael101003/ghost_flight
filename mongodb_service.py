import os
import logging
from typing import List, Dict, Optional
from pymongo import MongoClient
import time

logger = logging.getLogger(__name__)

class MongoDBService:
    """Servicio para interactuar con MongoDB para almacenamiento de vuelos"""
    
    def __init__(self, uri: str = None):
        self.uri = uri or os.environ.get("MONGODB_URI")
        self.client = None
        self.db = None
        
        if not self.uri:
            logger.warning("MONGODB_URI no configurada. El almacenamiento persistente estará deshabilitado.")
            return
        
        try:
            self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self.client.server_info()  # Test connection
            self.db = self.client.get_default_database()
            logger.info("✅ Conectado a MongoDB correctamente")
        except Exception as e:
            logger.error(f"❌ Error al conectar a MongoDB: {e}")
            self.client = None
            self.db = None
    
    def is_available(self) -> bool:
        """Verifica si MongoDB está disponible"""
        return self.db is not None
    
    def upsert_flight(self, flight_data: Dict) -> bool:
        """Inserta o actualiza datos de un vuelo"""
        if not self.is_available():
            return False
        
        try:
            collection = self.db.get_collection("flights")
            collection.update_one(
                {"icao24": flight_data.get("icao24")},
                {"$set": flight_data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error(f"Error al guardar vuelo: {e}")
            return False
    
    def get_flight_by_icao24(self, icao24: str) -> Optional[Dict]:
        """Obtiene un vuelo por su ICAO24"""
        if not self.is_available():
            return None
        
        try:
            collection = self.db.get_collection("flights")
            return collection.find_one({"icao24": icao24})
        except Exception as e:
            logger.error(f"Error al obtener vuelo: {e}")
            return None
    
    def get_all_flights(self) -> List[Dict]:
        """Obtiene todos los vuelos"""
        if not self.is_available():
            return []
        
        try:
            collection = self.db.get_collection("flights")
            return list(collection.find())
        except Exception as e:
            logger.error(f"Error al obtener vuelos: {e}")
            return []
    
    def get_flights_by_type(self, flight_type: str) -> List[Dict]:
        """Obtiene vuelos filtrados por tipo"""
        if not self.is_available():
            return []
        
        try:
            collection = self.db.get_collection("flights")
            return list(collection.find({"type": flight_type}))
        except Exception as e:
            logger.error(f"Error al filtrar vuelos: {e}")
            return []
    
    def get_historical_data(self, hours: int = 24) -> List[Dict]:
        """Obtiene datos históricos de las últimas N horas"""
        if not self.is_available():
            return []
        
        try:
            collection = self.db.get_collection("flights")
            cutoff_time = int(time.time()) - (hours * 3600)
            return list(collection.find({"fetched_at": {"$gte": cutoff_time}}))
        except Exception as e:
            logger.error(f"Error al obtener datos históricos: {e}")
            return []
