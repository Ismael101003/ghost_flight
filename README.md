# Ghost Flight 

Este proyecto muestra las posiciones de vuelos en vivo dentro de un área delimitada de México, utilizando la API de OpenSky, una pequeña aplicación Flask, **MongoDB Atlas para persistencia**, y **Zabbix para monitoreo de métricas**.

-----

## 💻 Componentes y Características

  - `app.py` — La aplicación Flask principal. [cite\_start]Ahora incluye manejo de token OAuth2, clasificación de vuelos (`carga`/`comercial`), persistencia opcional en MongoDB, y utiliza `pyzabbix` para **enviar métricas al Zabbix Trapper**[cite: 1].
      - Endpoints clave: `/vuelos`, `/vuelos/comerciales`, `/vuelos/carga`, `/ruta_vuelo/<icao24>`.
  - `collector.py` — Un script en segundo plano que consulta periódicamente OpenSky y actualiza los datos por aeronave en la colección `flights` de MongoDB.
  - `data/operator_mapping.json` — Archivo con prefijos de operadores utilizados para la clasificación de vuelos.
  - `mapa.html` — Archivo frontend que utiliza Leaflet. Ha sido actualizado para usar diferentes iconos para vuelos de carga/comerciales y se sugiere aumentar el intervalo de actualización para respetar los límites de la API.
  - `tests/test_classify.py` — Pruebas unitarias para la función de clasificación.

-----

## ⚙️ Variables de Entorno (Recomendado)

Estas variables deben definirse en tu terminal de PowerShell antes de ejecutar los scripts.

  - `OPENSKY_CLIENT_ID` y `OPENSKY_CLIENT_SECRET` — Credenciales OAuth del cliente OpenSky.
  - `MONGODB_URI` — Cadena de conexión de MongoDB Atlas (ej: `mongodb+srv://usuario:pass@cluster0/...`). [cite\_start]Habilita el almacenamiento persistente si se establece[cite: 1].
  - **`ZABBIX_SERVER`** — El Host o DNS de tu servidor Zabbix (ej: `smart-ibex.zabbix.cloud`).
  - [cite\_start]**`ZABBIX_HOST_NAME`** — El nombre del Host configurado en Zabbix para recibir las métricas Trapper (debe ser **`Ghost Flight App`**)[cite: 1].
  - `COLLECT_INTERVAL` — Segundos entre las consultas del colector (por defecto 15).

-----

## 🚀 Ejecución Local (PowerShell)

### 1\. Instalación de Dependencias

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Instala la librería para Zabbix:
pip install pyzabbix
```

### 2\. Ejecutar el Servidor Flask (Terminal 1)

**Abre la carpeta del proyecto** en PowerShell y ejecuta:

```powershell
# 1. Define las variables de entorno
$env:MONGODB_URI = "tu_uri_de_mongodb_atlas"
$env:ZABBIX_SERVER = "tu_servidor_de_zabbix.cloud"
$env:ZABBIX_HOST_NAME = "Ghost Flight App"

# 2. Inicia el servidor Flask
.\start_server.ps1
```

### 3\. Ejecutar el Colector (Terminal 2)

**Abre otra terminal** en la carpeta del proyecto y ejecuta:

```powershell
# 1. Asegúrate de definir MONGODB_URI en esta terminal también
$env:MONGODB_URI = "tu_uri_de_mongodb_atlas"

# 2. Inicia el colector
.\start_collector.ps1
```

-----

## 📝 Notas y Próximos Pasos

  - [cite\_start]**Monitoreo Completo:** La aplicación envía el conteo de vuelos (`flights.carga.count` y `flights.comercial.count`) a Zabbix para visualización y alertas[cite: 1].
  - **Tasa de Peticiones:** El intervalo de actualización del mapa (`mapa.html`) debe ajustarse (ej: a 30 segundos) para evitar el error `429 TOO MANY REQUESTS` de OpenSky.
  - Se recomienda agregar archivos Docker o servicios `systemd` para despliegue en producción del colector y la aplicación.
