# GhostFlight - Sistema de Rastreo de Vuelos con IA

Sistema de monitoreo de vuelos en tiempo real para México con análisis inteligente mediante Gemini API y alertas de voz con ElevenLabs.

## Características Principales

### Monitoreo en Tiempo Real
- Rastreo de vuelos comerciales y de carga en México
- Visualización en mapa interactivo con Leaflet
- Actualización automática cada 3 segundos
- Clasificación inteligente de vuelos

### Análisis con IA (Gemini API)
- **Análisis de vuelos individuales**: Evaluación de patrones de comportamiento
- **Análisis de tráfico**: Detección de patrones y anomalías en tiempo real
- **Chatbot inteligente**: Asistente virtual para consultas sobre vuelos
- **Predicciones**: Análisis predictivo basado en datos históricos

### Alertas Inteligentes
- Sistema de alertas configurable
- Detección de vuelos de carga
- Alertas de altitud baja
- Alertas de velocidad anormal
- Alertas de alto tráfico
- **Alertas de voz con ElevenLabs**: Narración natural en español de alertas críticas

### Base de Datos
- Almacenamiento persistente en MongoDB
- Historial de vuelos para análisis
- Caché de datos para optimización

## Requisitos

### APIs Requeridas
- **OpenSky Network API**: Para datos de vuelos (incluye credenciales OAuth)
- **Gemini API** (opcional pero recomendado): Para análisis con IA
- **ElevenLabs API** (opcional): Para alertas de voz
- **MongoDB** (opcional): Para almacenamiento persistente

### Dependencias
\`\`\`bash
pip install -r requirements.txt
\`\`\`

Principales dependencias:
- Flask: Framework web
- pymongo: Cliente de MongoDB
- requests: Cliente HTTP
- google-generativeai: SDK de Gemini API
- elevenlabs: SDK de ElevenLabs

## Configuración

### Variables de Entorno

Crea un archivo `.env` o configura las siguientes variables:

\`\`\`bash
# OpenSky Network (Requerido)
OPENSKY_CLIENT_ID=tu_client_id
OPENSKY_CLIENT_SECRET=tu_client_secret

# Gemini API (Recomendado)
GEMINI_API_KEY=tu_gemini_api_key

# ElevenLabs (Opcional)
ELEVENLABS_API_KEY=tu_elevenlabs_api_key
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM  # Opcional: ID de voz personalizada

# MongoDB (Opcional)
MONGODB_URI=mongodb://localhost:27017/ghostflight

# Zabbix (Opcional)
ZABBIX_API=tu_zabbix_api_url
ZABBIX_USER=tu_usuario
ZABBIX_PASS=tu_contraseña

# Colector
COLLECT_INTERVAL=15  # Intervalo en segundos
\`\`\`

### Obtener API Keys

#### Gemini API
1. Ve a [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Crea una API key
3. Copia y pega en `GEMINI_API_KEY`

#### ElevenLabs
1. Regístrate en [ElevenLabs](https://elevenlabs.io/)
2. Ve a tu perfil y obtén tu API key
3. Copia y pega en `ELEVENLABS_API_KEY`
4. (Opcional) Selecciona una voz y copia su ID en `ELEVENLABS_VOICE_ID`

## Instalación y Uso

### 1. Instalar dependencias
\`\`\`bash
pip install -r requirements.txt
\`\`\`

### 2. Configurar variables de entorno
\`\`\`bash
# En Windows
set GEMINI_API_KEY=tu_api_key
set ELEVENLABS_API_KEY=tu_api_key

# En Linux/Mac
export GEMINI_API_KEY=tu_api_key
export ELEVENLABS_API_KEY=tu_api_key
\`\`\`

### 3. Iniciar el servidor Flask
\`\`\`bash
python app.py
\`\`\`
O usando el script de PowerShell:
```powershell
.\start_server.ps1
