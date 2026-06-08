# ChatLamport

Aplicacion de mensajeria privada en tiempo real, desarrollada con Flask y WebSockets, disenada para desplegarse en Azure App Service.

---

## Descripcion general

ChatLamport permite a multiples usuarios registrarse, iniciar sesion y enviarse mensajes privados en tiempo real. Ademas de texto, los usuarios pueden compartir archivos de hasta 10 MB, incluyendo imagenes, videos, audio y documentos, con visualizacion directa dentro del chat sin necesidad de descargarlos.

La aplicacion mantiene el historial de mensajes y archivos durante la sesion activa del servidor. Al apagar el servidor, los mensajes y archivos se eliminan automaticamente, aunque los registros de usuario se conservan.

---

## Arquitectura

- **Backend**: Python con Flask y Flask-SocketIO
- **Comunicacion en tiempo real**: WebSockets mediante Socket.IO (modo `eventlet` en Azure, `threading` en local)
- **Base de datos**: SQLite, almacenada en `/home/site/wwwroot/database/chat.db` en Azure o en `database/chat.db` en local
- **Autenticacion**: Contrasenas hasheadas con bcrypt y sesiones de Flask
- **Frontend**: HTML, CSS y JavaScript puro (sin frameworks)

---

## Requisitos

- Python 3.10 o superior
- pip

Las dependencias se instalan con:

```
pip install -r requirements.txt
```

Paquetes utilizados:

| Paquete | Version |
|---|---|
| Flask | 3.0.0 |
| Flask-SocketIO | 5.3.6 |
| python-socketio | 5.10.0 |
| eventlet | 0.33.3 |
| bcrypt | 4.1.0 |

---

## Ejecucion local

```bash
python app.py
```

El servidor se levanta en `http://localhost:8000`.

---

## Despliegue en Azure App Service

El proyecto esta disenado para ejecutarse directamente en Azure App Service con Linux.

### Pasos

1. Crear un recurso de Azure App Service con runtime Python 3.10+.
2. Subir el codigo al repositorio conectado al App Service (GitHub Actions, ZIP deploy o Azure CLI).
3. Configurar el comando de inicio en la seccion **Configuration > General settings > Startup Command**:

```
bash startup.sh
```

### startup.sh

El archivo `startup.sh` es el punto de entrada automatico que Azure ejecuta al iniciar o reiniciar la instancia. Realiza tres acciones:

1. Instala las dependencias declaradas en `requirements.txt`.
2. Crea el directorio `/home/site/wwwroot/database` si no existe (necesario para la base de datos SQLite).
3. Lanza la aplicacion con `python app.py`.

```bash
#!/bin/bash
pip install -r requirements.txt
mkdir -p /home/site/wwwroot/database
python app.py
```

Azure detecta automaticamente la variable de entorno `WEBSITE_HOSTNAME` y la aplicacion cambia el modo asincrono a `eventlet` y apunta la base de datos a la ruta persistente del servicio.

### Variable de entorno recomendada

En **Configuration > Application settings** se recomienda definir:

| Variable | Descripcion |
|---|---|
| `SECRET_KEY` | Clave secreta de Flask para firmar sesiones. Si no se define, se genera una aleatoria al iniciar (las sesiones se invalidan al reiniciar). |
| `PORT` | Puerto de escucha. Azure lo asigna automaticamente; no es necesario definirlo manualmente. |

---

## Endpoints HTTP

| Metodo | Ruta | Descripcion |
|---|---|---|
| GET | `/` | Pagina principal de la aplicacion |
| GET | `/health` | Health check para Azure (retorna estado y timestamp) |
| POST | `/api/register` | Registro de nuevo usuario |
| POST | `/api/login` | Inicio de sesion |
| POST | `/api/logout` | Cierre de sesion |
| GET | `/api/usuarios` | Lista de usuarios registrados |
| GET | `/api/mensajes/<destino>` | Historial de mensajes con un usuario |
| GET | `/api/archivos/<destino>` | Historial de archivos intercambiados con un usuario |
| GET | `/api/mensajes/no_leidos` | Conteo de mensajes no leidos por remitente |

---

## Eventos WebSocket

| Evento (cliente -> servidor) | Descripcion |
|---|---|
| `join` | El cliente se une a la sala privada del chat seleccionado |
| `private_message` | Envia un mensaje de texto a otro usuario |
| `send_file` | Envia un archivo codificado en base64 |

| Evento (servidor -> cliente) | Descripcion |
|---|---|
| `usuarios_online` | Lista completa de usuarios conectados |
| `usuario_conectado` | Notificacion cuando un usuario se conecta |
| `usuario_desconectado` | Notificacion cuando un usuario se desconecta |
| `new_message` | Nuevo mensaje de texto en una sala |
| `new_file` | Nuevo archivo en una sala |
| `mensaje_recibido` | Notificacion directa al destinatario |

---

## Envio y visualizacion de archivos

Los archivos se transfieren codificados en base64 a traves del WebSocket y se almacenan en la base de datos durante la sesion activa del servidor.

**Tamano maximo por archivo: 10 MB**

El visualizador en el chat reconoce el tipo MIME del archivo y lo presenta de la siguiente forma:

| Tipo de archivo | Visualizacion |
|---|---|
| Imagenes (image/*) | Miniatura inline clicable que abre la imagen en tamano completo |
| Videos (video/*) | Reproductor de video con controles integrado en la burbuja |
| Audio (audio/*) | Reproductor de audio con controles integrado en la burbuja |
| PDF (application/pdf) | Vista previa embebida con enlace de descarga |
| Otros documentos y archivos | Enlace de descarga directa |

Formatos aceptados en el selector de archivos: imagenes, videos, audio, PDF, Word, Excel, PowerPoint, TXT, ZIP y RAR.

---

## Base de datos

Se utilizan tres tablas SQLite:

- **usuarios**: almacena nombre de usuario y contrasena hasheada.
- **mensajes**: almacena mensajes de texto con remitente, destinatario, contenido, timestamp y estado de lectura.
- **archivos**: almacena los archivos enviados con remitente, destinatario, nombre, tipo MIME, datos en base64 y timestamp.

Al apagar el servidor (SIGTERM, SIGINT o salida normal), los registros de `mensajes` y `archivos` se eliminan. Los usuarios registrados se conservan.

---

## Estructura del proyecto

```
ProyectoFinal_web/
|-- app.py                  # Servidor principal (Flask + SocketIO)
|-- startup.sh              # Script de inicio para Azure App Service
|-- requirements.txt        # Dependencias de Python
|-- database/
|   `-- chat.db             # Base de datos SQLite (generada automaticamente)
|-- static/
|   |-- css/                # Estilos de la interfaz
|   `-- js/
|       `-- chat.js         # Logica del cliente (WebSocket, UI, visualizador)
|-- templates/
|   `-- index.html          # Pagina unica de la aplicacion
`-- azure/
    `-- config.json         # Configuracion adicional de Azure
```
