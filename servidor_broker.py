"""
============================================================
  SERVIDOR BROKER - Chat tipo Telegram con Reloj Vectorial
  Protocolo: MSG|origen|destino|lamport|vector|timestamp|contenido
  Soporta: mensajes directos, archivos, multi-usuario, misma red
============================================================
"""

import socket
import threading
import json
import time
import os
import base64
import logging
from datetime import datetime

# ──────────────────────────────────────────────
#  CONFIGURACIÓN
# ──────────────────────────────────────────────
HOST     = "0.0.0.0"   # acepta conexiones de toda la red local
PORT     = 5000
NOMBRE   = "BROKER"
LOG_FILE = "broker.log"
TEMP_DIR = "archivos_temporales"  # carpeta donde se guardan archivos enviados

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(NOMBRE)


# ──────────────────────────────────────────────
#  RELOJ VECTORIAL
# ──────────────────────────────────────────────
class RelojVectorial:
    """
    Reloj Vectorial (Vector Clock).
    Mantiene un diccionario {proceso: contador}.
    Reglas:
      - Evento local       → incrementa propio contador
      - Enviar mensaje     → incrementa propio, adjunta copia del vector
      - Recibir mensaje    → por cada proceso: max(local, recibido) + 1 en propio
    """
    def __init__(self, nombre: str):
        self.nombre   = nombre
        self.vector   = {}          # {nombre_proceso: int}
        self._lock    = threading.Lock()

    def _asegurar(self, proceso: str):
        if proceso not in self.vector:
            self.vector[proceso] = 0

    def evento_local(self) -> dict:
        with self._lock:
            self._asegurar(self.nombre)
            self.vector[self.nombre] += 1
            log.info(f"[{self.nombre}] Evento local → {self.vector}")
            return dict(self.vector)

    def enviar(self, contenido: str) -> dict:
        with self._lock:
            self._asegurar(self.nombre)
            self.vector[self.nombre] += 1
            log.info(f"[{self.nombre}] Envía '{contenido[:40]}' → vector={self.vector}")
            return dict(self.vector)

    def recibir(self, vector_recibido: dict, remitente: str) -> dict:
        with self._lock:
            # Fusionar: max componente a componente
            for proc, ts in vector_recibido.items():
                self._asegurar(proc)
                self.vector[proc] = max(self.vector[proc], ts)
            # Incrementar propio
            self._asegurar(self.nombre)
            self.vector[self.nombre] += 1
            log.info(f"[{self.nombre}] Recibe de '{remitente}' -> {self.vector}")
            return dict(self.vector)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self.vector)

    # Comparación causal: ¿a ocurrió antes que b?
    @staticmethod
    def antes_que(a: dict, b: dict) -> bool:
        procs = set(a) | set(b)
        menor_o_igual = all(a.get(p, 0) <= b.get(p, 0) for p in procs)
        estrictamente  = any(a.get(p, 0) <  b.get(p, 0) for p in procs)
        return menor_o_igual and estrictamente

    @staticmethod
    def concurrentes(a: dict, b: dict) -> bool:
        return (not RelojVectorial.antes_que(a, b) and
                not RelojVectorial.antes_que(b, a))


# ──────────────────────────────────────────────
#  HISTORIAL DE MENSAJES (almacenamiento temporal)
# ──────────────────────────────────────────────
class Historial:
    """Guarda todos los mensajes en RAM y permite consultarlos."""
    def __init__(self):
        self._mensajes: list[dict] = []
        self._lock = threading.Lock()

    def agregar(self, msg: dict):
        with self._lock:
            self._mensajes.append(msg)

    def para_usuario(self, usuario: str) -> list[dict]:
        """Mensajes donde el usuario es origen O destino, o destino=='TODOS'."""
        with self._lock:
            return [m for m in self._mensajes
                    if m["origen"] == usuario
                    or m["destino"] == usuario
                    or m["destino"] == "TODOS"]

    def todos(self) -> list[dict]:
        with self._lock:
            return list(self._mensajes)


# ──────────────────────────────────────────────
#  SERVIDOR BROKER
# ──────────────────────────────────────────────
class ServidorBroker:
    def __init__(self):
        self.reloj    = RelojVectorial(NOMBRE)
        self.historial = Historial()

        # {nombre_usuario: socket}
        self.clientes: dict[str, socket.socket] = {}
        self._lock    = threading.Lock()

        os.makedirs(TEMP_DIR, exist_ok=True)

    # ── Registrar / desregistrar ──────────────────
    def registrar(self, nombre: str, sock: socket.socket):
        with self._lock:
            self.clientes[nombre] = sock
        log.info(f"Usuario '{nombre}' conectado. Activos: {list(self.clientes)}")
        self._broadcast_lista_usuarios()

    def desregistrar(self, nombre: str):
        with self._lock:
            self.clientes.pop(nombre, None)
        log.info(f"Usuario '{nombre}' desconectado. Activos: {list(self.clientes)}")
        self._broadcast_lista_usuarios()

    # ── Lista de usuarios conectados ──────────────
    def _broadcast_lista_usuarios(self):
        with self._lock:
            usuarios = list(self.clientes.keys())
        payload = self._crear_paquete(
            tipo="USUARIOS",
            origen=NOMBRE,
            destino="TODOS",
            contenido=json.dumps(usuarios)
        )
        self._enviar_a_todos(payload, excluir=None)

    # ── Crear paquete protocolo ───────────────────
    def _crear_paquete(self, tipo: str, origen: str, destino: str,
                       contenido: str, lamport: int = None) -> str:
        vector = self.reloj.enviar(contenido)
        lam    = lamport if lamport is not None else max(vector.values(), default=0)
        ts     = int(time.time())
        vector_str = json.dumps(vector, separators=(',', ':'))
        return f"{tipo}|{origen}|{destino}|{lam}|{vector_str}|{ts}|{contenido}"

    # ── Procesar mensaje entrante ─────────────────
    def procesar(self, raw: str, remitente_sock: socket.socket):
        partes = raw.split("|", 6)
        if len(partes) < 7:
            log.warning(f"Paquete malformado: {raw[:80]}")
            return

        tipo, origen, destino, lam_str, vector_str, ts_str, contenido = partes

        try:
            lam_recibido    = int(lam_str)
            vector_recibido = json.loads(vector_str)
        except Exception:
            vector_recibido = {}
            lam_recibido    = 0

        # Actualizar reloj vectorial del broker
        self.reloj.recibir(vector_recibido, origen)

        log.info(f"PKT [{tipo}] {origen}→{destino} lam={lam_recibido} "
                 f"vec={vector_recibido} | {contenido[:60]}")

        # ── Despachar por tipo ────────────────────
        if tipo == "CONNECT":
            self.registrar(contenido.strip(), remitente_sock)
            # Enviar historial al nuevo usuario
            self._enviar_historial(contenido.strip(), remitente_sock)

        elif tipo == "MSG":
            msg_dict = {
                "tipo": tipo, "origen": origen, "destino": destino,
                "lamport": lam_recibido, "vector": vector_recibido,
                "timestamp": ts_str, "contenido": contenido
            }
            self.historial.agregar(msg_dict)

            if destino == "TODOS":
                self._enviar_a_todos(raw, excluir=remitente_sock)
            else:
                self._entregar_a(destino, raw)
                # Eco al emisor con confirmación
                confirmacion = self._crear_paquete(
                    tipo="ACK", origen=NOMBRE, destino=origen,
                    contenido=f"Mensaje entregado a {destino}"
                )
                self._enviar_socket(remitente_sock, confirmacion)

        elif tipo == "FILE":
            self._manejar_archivo(origen, destino, contenido, remitente_sock)

        elif tipo == "HISTORY":
            self._enviar_historial(origen, remitente_sock)

        elif tipo == "PING":
            pong = self._crear_paquete("PONG", NOMBRE, origen, "pong")
            self._enviar_socket(remitente_sock, pong)

    # ── Enviar historial ──────────────────────────
    def _enviar_historial(self, usuario: str, sock: socket.socket):
        msgs = self.historial.para_usuario(usuario)
        payload = json.dumps(msgs, ensure_ascii=False)
        paquete = self._crear_paquete("HISTORY", NOMBRE, usuario, payload)
        self._enviar_socket(sock, paquete)

    # ── Manejo de archivos ────────────────────────
    def _manejar_archivo(self, origen: str, destino: str,
                         contenido: str, remitente_sock: socket.socket):
        """
        contenido = JSON: {"nombre": "foto.png", "datos": "<base64>"}
        El broker guarda el archivo y reenvía el paquete al destino.
        """
        try:
            meta    = json.loads(contenido)
            nombre  = meta["nombre"]
            datos   = base64.b64decode(meta["datos"])
            ruta    = os.path.join(TEMP_DIR, f"{int(time.time())}_{nombre}")
            with open(ruta, "wb") as f:
                f.write(datos)
            log.info(f"Archivo guardado temporalmente: {ruta}")
        except Exception as e:
            log.error(f"Error al guardar archivo: {e}")

        # Reenviar al destino
        raw = self._crear_paquete("FILE", origen, destino, contenido)
        if destino == "TODOS":
            self._enviar_a_todos(raw, excluir=remitente_sock)
        else:
            self._entregar_a(destino, raw)

    # ── Transporte ────────────────────────────────
    def _enviar_socket(self, sock: socket.socket, mensaje: str):
        try:
            sock.sendall((mensaje + "\n").encode("utf-8"))
        except Exception as e:
            log.error(f"Error al enviar: {e}")

    def _entregar_a(self, usuario: str, mensaje: str):
        with self._lock:
            sock = self.clientes.get(usuario)
        if sock:
            self._enviar_socket(sock, mensaje)
        else:
            log.warning(f"Usuario '{usuario}' no encontrado para entrega.")

    def _enviar_a_todos(self, mensaje: str, excluir: socket.socket | None):
        with self._lock:
            sockets = list(self.clientes.values())
        for sock in sockets:
            if sock != excluir:
                self._enviar_socket(sock, mensaje)

    # ── Hilo por cliente ──────────────────────────
    def _atender_cliente(self, sock: socket.socket, addr):
        log.info(f"Conexión entrante desde {addr}")
        nombre_usuario = None
        buffer = ""
        try:
            while True:
                datos = sock.recv(65536)
                if not datos:
                    break
                buffer += datos.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    linea, buffer = buffer.split("\n", 1)
                    linea = linea.strip()
                    if not linea:
                        continue
                    # Detectar nombre para CONNECT
                    partes = linea.split("|", 6)
                    if len(partes) >= 7 and partes[0] == "CONNECT":
                        nombre_usuario = partes[6].strip()
                    self.procesar(linea, sock)
        except Exception as e:
            log.error(f"Error con {addr}: {e}")
        finally:
            if nombre_usuario:
                self.desregistrar(nombre_usuario)
            sock.close()
            log.info(f"Conexión cerrada: {addr}")

    # ── Arrancar servidor ─────────────────────────
    def iniciar(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(20)  # hasta 20 conexiones simultáneas en cola

        log.info("=" * 50)
        log.info(f"  BROKER iniciado en {HOST}:{PORT}")
        log.info(f"  IP local: {socket.gethostbyname(socket.gethostname())}")
        log.info(f"  Archivos temporales en: {os.path.abspath(TEMP_DIR)}")
        log.info("=" * 50)

        while True:
            try:
                sock, addr = srv.accept()
                t = threading.Thread(
                    target=self._atender_cliente,
                    args=(sock, addr),
                    daemon=True
                )
                t.start()
            except KeyboardInterrupt:
                log.info("Broker detenido por el usuario.")
                break
        srv.close()


if __name__ == "__main__":
    ServidorBroker().iniciar()