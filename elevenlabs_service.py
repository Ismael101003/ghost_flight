import os
import logging
import requests
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class ElevenLabsService:
    """Servicio para generar alertas de voz usando ElevenLabs API"""
    
    def __init__(self):
        self.api_key = os.environ.get("ELEVENLABS_API_KEY")
        self.voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel voice por defecto
        
        if not self.api_key:
            logger.warning("ELEVENLABS_API_KEY no configurada. Las alertas de voz estarán deshabilitadas.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info("ElevenLabs API configurada correctamente")
    
    def is_available(self) -> bool:
        """Verifica si el servicio está disponible"""
        return self.enabled
    
    def generate_alert_audio(self, alert_text: str, alert_type: str = "warning") -> Optional[bytes]:
        """Genera audio para una alerta usando ElevenLabs"""
        if not self.is_available():
            return None
        
        try:
            # Ajustar el tono según el tipo de alerta
            stability = 0.5
            similarity_boost = 0.75
            
            if alert_type == "danger":
                stability = 0.3  # Más urgente
                similarity_boost = 0.9
            elif alert_type == "info":
                stability = 0.7  # Más calmado
                similarity_boost = 0.6
            
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
            
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": self.api_key
            }
            
            data = {
                "text": alert_text,
                "model_id": "eleven_multilingual_v2",  # Soporte para español
                "voice_settings": {
                    "stability": stability,
                    "similarity_boost": similarity_boost
                }
            }
            
            response = requests.post(url, json=data, headers=headers, timeout=10)
            
            if response.status_code == 200:
                logger.info(f"Audio generado exitosamente para alerta: {alert_text[:50]}...")
                return response.content
            else:
                logger.error(f"Error al generar audio: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Error al generar audio con ElevenLabs: {e}")
            return None
    
    def create_alert_narration(self, alert: Dict) -> Optional[str]:
        """Crea una narración natural para una alerta"""
        alert_type = alert.get('type', 'unknown')
        severity = alert.get('severity', 'info')
        message = alert.get('message', '')
        
        # Crear narración más natural en español
        narrations = {
            'cargo_entry': f"Atención. {message}. Se recomienda verificar.",
            'high_count': f"Información. {message}. El tráfico está por encima del promedio.",
            'low_altitude': f"Alerta de seguridad. {message}. Esto podría requerir atención inmediata.",
            'abnormal_speed': f"Advertencia. {message}. Se detectó velocidad fuera de rango normal."
        }
        
        return narrations.get(alert_type, f"Alerta del sistema. {message}")
