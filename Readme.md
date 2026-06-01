# ChatLamport — Sistema de Chat con Reloj Vectorial

Chat tipo Telegram en red local con mensajes directos,
transferencia de archivos y sincronización con Reloj Vectorial.

---

## Archivos

| Archivo | Descripción |
|---|---|
| `servidor_broker.py` | Servidor intermediario (Python). Córrelo en la máquina "broker". |
| `cliente_gui.py` | Cliente con GUI tkinter (para tu amiga y otros usuarios Python). |
| `cliente_csharp.cs` | Cliente consola C# (tu máquina). |

---

## Requisitos

- **Python 3.11+** — solo librería estándar (sin pip install)
- **C# / .NET 7+** — solo System.Text.Json (incluido en el SDK)
- Todos en la **misma red local** (WiFi o LAN)

---

## Paso a paso

### 1. Averigua la IP del broker

En la máquina donde vas a correr el servidor, ejecuta:

```bash
# Windows
ipconfig

# Linux / macOS
hostname -I
```

Anota la IP local, por ejemplo: `192.168.1.50`

---

### 2. Arranca el servidor broker (Python)

```bash
python3 servidor_broker.py
```

Verás algo como:
```
==================================================
  BROKER iniciado en 0.0.0.0:5000
  IP local: 192.168.1.50
  Archivos temporales en: /ruta/archivos_temporales
==================================================
```

---

### 3. Configura la IP en los clientes

**En `cliente_gui.py`** (primera línea de configuración):
```python
BROKER_HOST = "192.168.1.50"   # ← IP del broker
```
O simplemente escríbela en la pantalla de login al abrir la app.

**En `cliente_csharp.cs`**:
```csharp
private static readonly string BROKER_HOST = "192.168.1.50"; // ← IP del broker
```

---

### 4. Compila y corre el cliente C#

#### Opción A — Proyecto nuevo (recomendado)
```bash
dotnet new console -n ClienteChat
cd ClienteChat
# Reemplaza Program.cs con el contenido de cliente_csharp.cs
dotnet run
```

#### Opción B — Compilar directo
```bash
csc cliente_csharp.cs -out:cliente.exe
./cliente.exe
```

---

### 5. Corre el cliente Python (tu amiga)

```bash
python3 cliente_gui.py
```

Se abre una ventana. Escribe el nombre de usuario, confirma la IP y presiona "Conectar".

---

## Cómo usar el chat

### Cliente Python (GUI)
- La barra lateral muestra todos los usuarios conectados
- Haz clic en un usuario para abrir la conversación
- Escribe y presiona **Enter** (Shift+Enter para salto de línea)
- 📎 para enviar archivos

### Cliente C# (consola)

```
/chat Ana          → empezar a chatear con Ana
/usuarios          → ver quién está conectado
/vector            → ver tu reloj vectorial actual
Hola!              → enviar mensaje al destinatario activo
/salir             → desconectar
```

---

## Protocolo de mensajes

```
TIPO|ORIGEN|DESTINO|LAMPORT|VECTOR_JSON|TIMESTAMP_UNIX|CONTENIDO
```

Ejemplos:
```
MSG|Carlos|Ana|3|{"Carlos":3,"Ana":1}|1717200000|Hola Ana!
FILE|Ana|Carlos|4|{"Carlos":3,"Ana":4}|1717200001|{"nombre":"foto.png","datos":"<base64>"}
CONNECT|BROKER|BROKER|0|{}|1717200000|Carlos
USUARIOS|BROKER|TODOS|1|{"BROKER":1}|1717200001|["Carlos","Ana"]
```

---

## Reloj Vectorial — Resumen

| Evento | Regla |
|---|---|
| Evento local | `vector[yo]++` |
| Enviar mensaje | `vector[yo]++`, adjuntar copia |
| Recibir mensaje | `∀p: vector[p] = max(local[p], recibido[p])`, luego `vector[yo]++` |

La relación causal `a → b` se cumple si `∀p: vector_a[p] ≤ vector_b[p]` y `∃p: vector_a[p] < vector_b[p]`.

---

## Más usuarios

Solo necesitan:
1. Estar en la misma red (WiFi/LAN)
2. Conocer la IP del broker
3. Correr `cliente_gui.py` o `cliente_csharp.cs`

El broker acepta hasta 20 conexiones simultáneas configurables.

---

## Archivos temporales

Los archivos enviados se guardan en `archivos_temporales/` en la máquina del broker
con el formato `<timestamp>_<nombre_original>`. Se eliminan manualmente.