import os
import logging
import json
from typing import List, Dict, Optional
import google.generativeai as genai

logger = logging.getLogger(__name__)

class GeminiService:
    """Servicio para interactuar con Gemini API para análisis de vuelos"""
    
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning("GEMINI_API_KEY no configurada. El servicio de análisis estará deshabilitado.")
            self.model = None
        else:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
            logger.info("Gemini API configurada correctamente")
    
    def is_available(self) -> bool:
        """Verifica si el servicio está disponible"""
        return self.model is not None
    
    def analyze_flight_pattern(self, flight_data: Dict) -> Optional[str]:
        """Analiza un vuelo individual y detecta patrones sospechosos"""
        if not self.is_available():
            return None
        
        try:
            prompt = f"""Eres un experto en análisis de tráfico aéreo. Analiza este vuelo y proporciona información relevante:

Datos del vuelo:
- Callsign: {flight_data.get('callsign', 'N/A')}
- Tipo: {flight_data.get('type', 'desconocido')}
- País de origen: {flight_data.get('origin_country', 'N/A')}
- Altitud actual: {flight_data.get('altitude', 'N/A')} pies
- Velocidad: {flight_data.get('velocity', 'N/A')} nudos
- Rumbo: {flight_data.get('heading', 'N/A')} grados

Por favor, proporciona un análisis breve (máximo 3-4 líneas) sobre:
1. Si la altitud y velocidad son normales para este tipo de vuelo
2. Cualquier comportamiento que pueda ser inusual
3. Información relevante sobre el operador o tipo de vuelo

Responde de forma concisa y profesional."""
            
            response = self.model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            logger.error(f"Error al analizar vuelo con Gemini: {e}")
            return None
    
    def analyze_traffic_pattern(self, flights: List[Dict], stats: Dict) -> Optional[str]:
        """Analiza patrones de tráfico general en el área"""
        if not self.is_available():
            return None
        
        try:
            # Resumen de datos
            cargo_flights = [f for f in flights if f.get('type') == 'carga']
            commercial_flights = [f for f in flights if f.get('type') == 'comercial']
            
            # Calcular estadísticas básicas
            avg_altitude = sum(f.get('altitude', 0) for f in flights if f.get('altitude')) / len(flights) if flights else 0
            avg_velocity = sum(f.get('velocity', 0) for f in flights if f.get('velocity')) / len(flights) if flights else 0
            
            prompt = f"""Eres un analista de tráfico aéreo experto. Analiza el siguiente patrón de vuelos en el área de México:

Estadísticas actuales:
- Total de vuelos: {len(flights)}
- Vuelos comerciales: {len(commercial_flights)}
- Vuelos de carga: {len(cargo_flights)}
- Altitud promedio: {avg_altitude:.0f} pies
- Velocidad promedio: {avg_velocity:.0f} nudos

Vuelos de carga detectados:
{chr(10).join([f"- {f.get('callsign', 'N/A')} ({f.get('origin_country', 'N/A')}) - Alt: {f.get('altitude', 'N/A')} ft" for f in cargo_flights[:5]])}

Por favor, proporciona un análisis ejecutivo (máximo 5-6 líneas) que incluya:
1. Evaluación del nivel de tráfico (bajo/normal/alto)
2. Patrones destacados en vuelos de carga
3. Cualquier anomalía o punto de interés
4. Recomendaciones de monitoreo

Responde de forma concisa y profesional."""
            
            response = self.model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            logger.error(f"Error al analizar patrones de tráfico con Gemini: {e}")
            return None
    
    def chat_query(self, query: str, context: Optional[Dict] = None) -> Optional[str]:
        """Responde preguntas sobre los datos de vuelos usando el contexto actual"""
        if not self.is_available():
            return "El servicio de análisis con IA no está disponible. Configura GEMINI_API_KEY para habilitarlo."
        
        try:
            # Construir prompt con contexto
            context_text = ""
            if context:
                context_text = f"""
Contexto actual del sistema:
- Total de vuelos activos: {context.get('total_flights', 0)}
- Vuelos comerciales: {context.get('commercial_flights', 0)}
- Vuelos de carga: {context.get('cargo_flights', 0)}
- Alertas recientes: {context.get('recent_alerts', 0)}
- Última actualización: {context.get('last_update', 'N/A')}
"""
            
            prompt = f"""Eres un asistente experto en aviación y análisis de tráfico aéreo para el sistema Ghost Flight, 
que monitorea vuelos en México en tiempo real usando datos de OpenSky Network.

{context_text}

Pregunta del usuario: {query}

Proporciona una respuesta clara, concisa y útil basada en el contexto disponible. 
Si necesitas más información para responder, indícalo claramente."""
            
            response = self.model.generate_content(prompt)
            return response.text
            
        except Exception as e:
            logger.error(f"Error en chat con Gemini: {e}")
            return f"Error al procesar la consulta: {str(e)}"
    
    def generate_response(self, prompt: str) -> Optional[str]:
        """Genera una respuesta usando Gemini con un prompt personalizado"""
        if not self.is_available():
            return None
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error al generar respuesta con Gemini: {e}")
            return None
    
    def predict_pattern(self, historical_data: List[Dict]) -> Optional[Dict]:
        """Analiza datos históricos y predice patrones futuros"""
        if not self.is_available():
            return None
        
        try:
            # Preparar resumen de datos históricos
            total_flights = len(historical_data)
            cargo_count = sum(1 for f in historical_data if f.get('tipo') == 'carga')
            
            # Agrupar por hora si hay timestamp
            hourly_distribution = {}
            for flight in historical_data:
                if 'fecha_captura' in flight:
                    from datetime import datetime
                    hour = datetime.fromtimestamp(flight['fecha_captura']).hour
                    hourly_distribution[hour] = hourly_distribution.get(hour, 0) + 1
            
            prompt = f"""Eres un analista predictivo de tráfico aéreo. Analiza estos datos históricos y proporciona predicciones:

Datos históricos analizados:
- Total de vuelos registrados: {total_flights}
- Vuelos de carga: {cargo_count} ({(cargo_count/total_flights*100):.1f}%)
- Distribución horaria: {json.dumps(hourly_distribution, indent=2)}

Basándote en estos patrones históricos, proporciona:
1. Predicción de tráfico para las próximas horas
2. Patrones de horarios pico identificados
3. Tendencias en vuelos de carga
4. Recomendaciones de monitoreo prioritario

Responde en formato JSON con las siguientes claves: prediction, peak_hours, cargo_trend, recommendations"""
            
            response = self.model.generate_content(prompt)
            
            # Intentar parsear como JSON
            try:
                # Extraer JSON del texto de respuesta
                text = response.text
                start = text.find('{')
                end = text.rfind('}') + 1
                if start != -1 and end > start:
                    json_str = text[start:end]
                    return json.loads(json_str)
                else:
                    return {"raw_analysis": text}
            except:
                return {"raw_analysis": response.text}
            
        except Exception as e:
            logger.error(f"Error en predicción de patrones: {e}")
            return None
