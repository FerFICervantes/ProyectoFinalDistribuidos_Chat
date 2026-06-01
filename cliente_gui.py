"""
============================================================
  CLIENTE PYTHON - Chat con GUI (tkinter) + Reloj Vectorial
  Conecta al broker en la misma red local.
  Ejecutar: python3 cliente_gui.py
============================================================
"""

import socket
import threading
import json
import time
import os
import base64
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from datetime import datetime


# ──────────────────────────────────────────────
#  CONFIGURACIÓN  (editar IP del broker)
# ──────────────────────────────────────────────
BROKER_HOST = "127.0.0.1"   # ← Cambia a la IP del servidor en tu red
BROKER_PORT = 5000


# ──────────────────────────────────────────────
#  RELOJ VECTORIAL (igual al del broker)
# ──────────────────────────────────────────────
class RelojVectorial:
    def __init__(self, nombre: str):
        self.nombre = nombre
        self.vector: dict[str, int] = {}
        self._lock  = threading.Lock()

    def _asegurar(self, p: str):
        if p not in self.vector:
            self.vector[p] = 0

    def enviar(self) -> dict:
        with self._lock:
            self._asegurar(self.nombre)
            self.vector[self.nombre] += 1
            return dict(self.vector)

    def recibir(self, vector_recibido: dict):
        with self._lock:
            for p, ts in vector_recibido.items():
                self._asegurar(p)
                self.vector[p] = max(self.vector[p], ts)
            self._asegurar(self.nombre)
            self.vector[self.nombre] += 1

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self.vector)


# ──────────────────────────────────────────────
#  LÓGICA DE RED
# ──────────────────────────────────────────────
class ConexionBroker:
    def __init__(self, nombre: str, on_mensaje, on_usuarios, on_historial, on_archivo):
        self.nombre       = nombre
        self.reloj        = RelojVectorial(nombre)
        self.sock: socket.socket | None = None
        self._on_mensaje  = on_mensaje
        self._on_usuarios = on_usuarios
        self._on_historial = on_historial
        self._on_archivo  = on_archivo
        self._conectado   = False

    def conectar(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((BROKER_HOST, BROKER_PORT))
            self._conectado = True
            # Registrar nombre en el broker
            self._enviar_paquete("CONNECT", NOMBRE_BROKER := "BROKER",
                                 destino="BROKER", contenido=self.nombre)
            # Hilo de recepción
            t = threading.Thread(target=self._recibir_loop, daemon=True)
            t.start()
            return True
        except Exception as e:
            print(f"Error al conectar: {e}")
            return False

    def desconectar(self):
        self._conectado = False
        if self.sock:
            self.sock.close()

    # ── Enviar ────────────────────────────────
    def _enviar_paquete(self, tipo: str, destino: str,
                        contenido: str, origen: str = None):
        if not origen:
            origen = self.nombre
        vector = self.reloj.enviar()
        lam    = vector.get(self.nombre, 0)
        ts     = int(time.time())
        vec_str = json.dumps(vector, separators=(',', ':'))
        paquete = f"{tipo}|{origen}|{destino}|{lam}|{vec_str}|{ts}|{contenido}\n"
        try:
            self.sock.sendall(paquete.encode("utf-8"))
        except Exception as e:
            print(f"Error al enviar: {e}")

    def enviar_mensaje(self, destino: str, contenido: str):
        self._enviar_paquete("MSG", destino, contenido)

    def enviar_archivo(self, destino: str, ruta_local: str):
        nombre_archivo = os.path.basename(ruta_local)
        with open(ruta_local, "rb") as f:
            datos_b64 = base64.b64encode(f.read()).decode("utf-8")
        payload = json.dumps({"nombre": nombre_archivo, "datos": datos_b64},
                              ensure_ascii=False)
        self._enviar_paquete("FILE", destino, payload)

    def pedir_historial(self):
        self._enviar_paquete("HISTORY", "BROKER", self.nombre)

    # ── Recibir ───────────────────────────────
    def _recibir_loop(self):
        buffer = ""
        while self._conectado:
            try:
                datos = self.sock.recv(65536)
                if not datos:
                    break
                buffer += datos.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    linea, buffer = buffer.split("\n", 1)
                    linea = linea.strip()
                    if linea:
                        self._procesar(linea)
            except Exception:
                break

    def _procesar(self, raw: str):
        partes = raw.split("|", 6)
        if len(partes) < 7:
            return
        tipo, origen, destino, lam_str, vec_str, ts_str, contenido = partes
        try:
            vector = json.loads(vec_str)
            lam    = int(lam_str)
        except Exception:
            vector, lam = {}, 0

        self.reloj.recibir(vector)

        if tipo == "MSG":
            self._on_mensaje(origen, destino, contenido, lam, vector, ts_str)
        elif tipo == "USUARIOS":
            try:
                lista = json.loads(contenido)
            except Exception:
                lista = []
            self._on_usuarios(lista)
        elif tipo == "HISTORY":
            try:
                msgs = json.loads(contenido)
            except Exception:
                msgs = []
            self._on_historial(msgs)
        elif tipo == "FILE":
            self._on_archivo(origen, destino, contenido, ts_str)
        elif tipo == "ACK":
            self._on_mensaje("✓ BROKER", destino, contenido, lam, vector, ts_str)


# ──────────────────────────────────────────────
#  GUI
# ──────────────────────────────────────────────
COLORES = {
    "bg":        "#0d1117",
    "sidebar":   "#161b22",
    "header":    "#1f2937",
    "burbuja_yo": "#2563eb",
    "burbuja_otro": "#1f2937",
    "texto":     "#f0f6fc",
    "texto_dim": "#8b949e",
    "acento":    "#3b82f6",
    "verde":     "#22c55e",
    "rojo":      "#ef4444",
    "borde":     "#30363d",
    "entrada":   "#21262d",
}

FUENTE_MSG  = ("Consolas", 11)
FUENTE_UI   = ("Segoe UI", 10)
FUENTE_BOLD = ("Segoe UI", 10, "bold")
FUENTE_PEQUEÑA = ("Segoe UI", 8)


class AppChat(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ChatLamport — Cliente Python")
        self.geometry("1000x680")
        self.configure(bg=COLORES["bg"])
        self.minsize(800, 500)

        self.nombre_usuario = None
        self.chat_activo    = None   # con quién estoy chateando ahora
        self.conversaciones: dict[str, list] = {}  # {usuario: [mensajes]}
        self.conexion: ConexionBroker | None = None

        self._pantalla_login()

    # ══════════════════════════════════════════
    #  PANTALLA DE LOGIN
    # ══════════════════════════════════════════
    def _pantalla_login(self):
        self._limpiar()
        frame = tk.Frame(self, bg=COLORES["bg"])
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(frame, text="💬 ChatLamport", font=("Segoe UI", 28, "bold"),
                 bg=COLORES["bg"], fg=COLORES["acento"]).pack(pady=(0, 4))
        tk.Label(frame, text="Reloj Vectorial · Mensajes Directos",
                 font=FUENTE_UI, bg=COLORES["bg"], fg=COLORES["texto_dim"]).pack(pady=(0, 30))

        tk.Label(frame, text="Tu nombre de usuario:",
                 font=FUENTE_UI, bg=COLORES["bg"], fg=COLORES["texto"]).pack(anchor="w")
        self._ent_nombre = tk.Entry(frame, font=("Segoe UI", 13),
                                    bg=COLORES["entrada"], fg=COLORES["texto"],
                                    insertbackground=COLORES["texto"],
                                    relief="flat", bd=8, width=28)
        self._ent_nombre.pack(pady=(4, 16))
        self._ent_nombre.focus()

        tk.Label(frame, text="IP del Broker:",
                 font=FUENTE_UI, bg=COLORES["bg"], fg=COLORES["texto"]).pack(anchor="w")
        self._ent_ip = tk.Entry(frame, font=("Segoe UI", 13),
                                bg=COLORES["entrada"], fg=COLORES["texto"],
                                insertbackground=COLORES["texto"],
                                relief="flat", bd=8, width=28)
        self._ent_ip.insert(0, BROKER_HOST)
        self._ent_ip.pack(pady=(4, 24))

        self._lbl_error = tk.Label(frame, text="", font=FUENTE_UI,
                                   bg=COLORES["bg"], fg=COLORES["rojo"])
        self._lbl_error.pack()

        btn = tk.Button(frame, text="Conectar →", font=FUENTE_BOLD,
                        bg=COLORES["acento"], fg="white", relief="flat",
                        padx=20, pady=10, cursor="hand2",
                        command=self._conectar)
        btn.pack(pady=8)
        self._ent_nombre.bind("<Return>", lambda e: self._conectar())

    def _conectar(self):
        nombre = self._ent_nombre.get().strip()
        ip     = self._ent_ip.get().strip()
        if not nombre:
            self._lbl_error.config(text="Escribe un nombre de usuario.")
            return
        global BROKER_HOST
        BROKER_HOST = ip

        self.nombre_usuario = nombre
        self.conexion = ConexionBroker(
            nombre,
            on_mensaje   = self._on_mensaje,
            on_usuarios  = self._on_usuarios,
            on_historial = self._on_historial,
            on_archivo   = self._on_archivo
        )
        if self.conexion.conectar():
            self._pantalla_chat()
        else:
            self._lbl_error.config(
                text=f"No se pudo conectar a {ip}:{BROKER_PORT}")

    # ══════════════════════════════════════════
    #  PANTALLA PRINCIPAL DE CHAT
    # ══════════════════════════════════════════
    def _pantalla_chat(self):
        self._limpiar()

        # ── Layout principal ──────────────────
        self._sidebar = tk.Frame(self, bg=COLORES["sidebar"], width=220)
        self._sidebar.pack(side="left", fill="y")
        self._sidebar.pack_propagate(False)

        self._area_chat = tk.Frame(self, bg=COLORES["bg"])
        self._area_chat.pack(side="left", fill="both", expand=True)

        # ── Sidebar: título + lista usuarios ─
        tk.Label(self._sidebar, text="👥 Usuarios en línea",
                 font=FUENTE_BOLD, bg=COLORES["sidebar"],
                 fg=COLORES["texto"], pady=12).pack(fill="x")

        sep = tk.Frame(self._sidebar, bg=COLORES["borde"], height=1)
        sep.pack(fill="x")

        self._lista_usuarios = tk.Listbox(
            self._sidebar, font=FUENTE_UI,
            bg=COLORES["sidebar"], fg=COLORES["texto"],
            selectbackground=COLORES["acento"],
            selectforeground="white",
            relief="flat", bd=0,
            activestyle="none",
            highlightthickness=0
        )
        self._lista_usuarios.pack(fill="both", expand=True, padx=4, pady=4)
        self._lista_usuarios.bind("<<ListboxSelect>>", self._seleccionar_usuario)

        tk.Label(self._sidebar, text=f"Tú: {self.nombre_usuario}",
                 font=FUENTE_PEQUEÑA, bg=COLORES["sidebar"],
                 fg=COLORES["verde"], pady=8).pack()

        # ── Área chat: header + mensajes + entrada ──
        self._header = tk.Frame(self._area_chat, bg=COLORES["header"], height=50)
        self._header.pack(fill="x")
        self._header.pack_propagate(False)

        self._lbl_chat_nombre = tk.Label(
            self._header, text="← Selecciona un usuario",
            font=FUENTE_BOLD, bg=COLORES["header"], fg=COLORES["texto"]
        )
        self._lbl_chat_nombre.pack(side="left", padx=16, pady=12)

        self._lbl_vector = tk.Label(
            self._header, text="Vector: {}",
            font=FUENTE_PEQUEÑA, bg=COLORES["header"], fg=COLORES["texto_dim"]
        )
        self._lbl_vector.pack(side="right", padx=16)

        # Canvas con scrollbar para burbujas
        self._canvas_frame = tk.Frame(self._area_chat, bg=COLORES["bg"])
        self._canvas_frame.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(self._canvas_frame,
                                  bg=COLORES["bg"], highlightthickness=0)
        self._scrollbar = ttk.Scrollbar(self._canvas_frame,
                                         orient="vertical",
                                         command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scrollbar.set)
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._msgs_frame = tk.Frame(self._canvas, bg=COLORES["bg"])
        self._canvas_win = self._canvas.create_window(
            (0, 0), window=self._msgs_frame, anchor="nw")
        self._msgs_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Entrada de texto
        entrada_frame = tk.Frame(self._area_chat,
                                  bg=COLORES["header"], pady=10)
        entrada_frame.pack(fill="x", side="bottom")

        self._texto_entrada = tk.Text(
            entrada_frame, font=FUENTE_MSG, height=2,
            bg=COLORES["entrada"], fg=COLORES["texto"],
            insertbackground=COLORES["texto"],
            relief="flat", bd=6, wrap="word"
        )
        self._texto_entrada.pack(side="left", fill="x", expand=True,
                                  padx=(12, 6), pady=4)
        self._texto_entrada.bind("<Return>", self._enviar_con_enter)
        self._texto_entrada.bind("<Shift-Return>", lambda e: None)

        btn_archivo = tk.Button(
            entrada_frame, text="📎", font=("Segoe UI", 14),
            bg=COLORES["entrada"], fg=COLORES["texto_dim"],
            relief="flat", bd=0, cursor="hand2",
            command=self._enviar_archivo
        )
        btn_archivo.pack(side="left", padx=4)

        btn_enviar = tk.Button(
            entrada_frame, text="➤", font=("Segoe UI", 14),
            bg=COLORES["acento"], fg="white",
            relief="flat", bd=0, padx=12, cursor="hand2",
            command=self._enviar_mensaje
        )
        btn_enviar.pack(side="left", padx=(0, 12))

    # ── Helpers canvas ────────────────────────
    def _on_frame_configure(self, event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._canvas_win, width=event.width)

    def _scroll_abajo(self):
        self._canvas.update_idletasks()
        self._canvas.yview_moveto(1.0)

    # ══════════════════════════════════════════
    #  CALLBACKS DE RED (hilo → GUI)
    # ══════════════════════════════════════════
    def _on_mensaje(self, origen, destino, contenido, lam, vector, ts_str):
        # Determinar a qué conversación pertenece
        if origen == self.nombre_usuario:
            chat_key = destino
        else:
            chat_key = origen

        if chat_key not in self.conversaciones:
            self.conversaciones[chat_key] = []

        self.conversaciones[chat_key].append({
            "origen": origen, "destino": destino,
            "contenido": contenido, "lam": lam,
            "vector": vector, "ts": ts_str, "tipo": "MSG"
        })

        self.after(0, lambda: self._actualizar_vector_label())
        if self.chat_activo == chat_key:
            self.after(0, lambda: self._agregar_burbuja(
                origen, contenido, lam, vector, ts_str))

    def _on_usuarios(self, lista: list):
        def _update():
            self._lista_usuarios.delete(0, tk.END)
            for u in lista:
                if u != self.nombre_usuario:
                    self._lista_usuarios.insert(tk.END, f"  🟢 {u}")
        self.after(0, _update)

    def _on_historial(self, msgs: list):
        def _update():
            for m in msgs:
                chat_key = (m["destino"] if m["origen"] == self.nombre_usuario
                            else m["origen"])
                if chat_key not in self.conversaciones:
                    self.conversaciones[chat_key] = []
                self.conversaciones[chat_key].append(m)
            if self.chat_activo:
                self._cargar_conversacion(self.chat_activo)
        self.after(0, _update)

    def _on_archivo(self, origen, destino, contenido, ts_str):
        def _guardar():
            try:
                meta   = json.loads(contenido)
                nombre = meta["nombre"]
                datos  = base64.b64decode(meta["datos"])
                ruta   = filedialog.asksaveasfilename(
                    defaultextension=os.path.splitext(nombre)[1],
                    initialfile=nombre,
                    title=f"Guardar archivo de {origen}"
                )
                if ruta:
                    with open(ruta, "wb") as f:
                        f.write(datos)
                    messagebox.showinfo("Archivo recibido",
                                        f"Archivo '{nombre}' guardado.")
            except Exception as e:
                messagebox.showerror("Error", f"No se pudo guardar: {e}")
        self.after(0, _guardar)

    # ══════════════════════════════════════════
    #  INTERACCIÓN DE USUARIO
    # ══════════════════════════════════════════
    def _seleccionar_usuario(self, event):
        sel = self._lista_usuarios.curselection()
        if not sel:
            return
        texto = self._lista_usuarios.get(sel[0]).strip()
        usuario = texto.replace("🟢 ", "").strip()
        self.chat_activo = usuario
        self._lbl_chat_nombre.config(text=f"💬 {usuario}")
        self._cargar_conversacion(usuario)

    def _cargar_conversacion(self, usuario: str):
        for w in self._msgs_frame.winfo_children():
            w.destroy()
        msgs = self.conversaciones.get(usuario, [])
        for m in msgs:
            self._agregar_burbuja(
                m.get("origen", "?"),
                m.get("contenido", ""),
                m.get("lam", 0) or m.get("lamport", 0),
                m.get("vector", {}),
                m.get("ts", "") or m.get("timestamp", "")
            )

    def _agregar_burbuja(self, origen: str, contenido: str,
                          lam: int, vector: dict, ts_str: str):
        es_mio = (origen == self.nombre_usuario)
        color  = COLORES["burbuja_yo"] if es_mio else COLORES["burbuja_otro"]
        anchor = "e" if es_mio else "w"
        lado   = "right" if es_mio else "left"

        outer = tk.Frame(self._msgs_frame, bg=COLORES["bg"])
        outer.pack(fill="x", padx=10, pady=3, anchor=anchor)

        if not es_mio:
            tk.Label(outer, text=origen, font=FUENTE_PEQUEÑA,
                     bg=COLORES["bg"], fg=COLORES["acento"]).pack(
                anchor="w", padx=4)

        burbuja = tk.Frame(outer, bg=color,
                            padx=12, pady=8)
        burbuja.pack(side=lado, anchor=anchor)

        tk.Label(burbuja, text=contenido,
                 font=FUENTE_MSG, bg=color, fg=COLORES["texto"],
                 wraplength=380, justify="left").pack(anchor="w")

        # Metadata: lamport + vector resumido
        try:
            ts_fmt = datetime.fromtimestamp(int(ts_str)).strftime("%H:%M")
        except Exception:
            ts_fmt = ""

        vec_corto = json.dumps(vector, separators=(',', ':')) if vector else "{}"
        meta_txt  = f"L={lam}  {vec_corto}  {ts_fmt}"
        tk.Label(burbuja, text=meta_txt,
                 font=FUENTE_PEQUEÑA, bg=color,
                 fg="#93c5fd" if es_mio else COLORES["texto_dim"]).pack(
            anchor="e", pady=(4, 0))

        self._scroll_abajo()

    def _actualizar_vector_label(self):
        if self.conexion:
            v = self.conexion.reloj.snapshot()
            self._lbl_vector.config(text=f"Vector: {json.dumps(v)}")

    def _enviar_con_enter(self, event):
        if not event.state & 0x1:  # Sin Shift
            self._enviar_mensaje()
            return "break"

    def _enviar_mensaje(self):
        if not self.chat_activo:
            messagebox.showwarning("Sin destino",
                                    "Selecciona un usuario de la lista.")
            return
        contenido = self._texto_entrada.get("1.0", tk.END).strip()
        if not contenido:
            return
        self.conexion.enviar_mensaje(self.chat_activo, contenido)
        self._texto_entrada.delete("1.0", tk.END)
        # Mostrar en UI local
        vector = self.conexion.reloj.snapshot()
        lam    = vector.get(self.nombre_usuario, 0)
        self._on_mensaje(self.nombre_usuario, self.chat_activo,
                          contenido, lam, vector, str(int(time.time())))

    def _enviar_archivo(self):
        if not self.chat_activo:
            messagebox.showwarning("Sin destino",
                                    "Selecciona un usuario primero.")
            return
        ruta = filedialog.askopenfilename(title="Seleccionar archivo")
        if not ruta:
            return
        try:
            self.conexion.enviar_archivo(self.chat_activo, ruta)
            messagebox.showinfo("Archivo enviado",
                                 f"'{os.path.basename(ruta)}' enviado a {self.chat_activo}.")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo enviar: {e}")

    # ── Utils ─────────────────────────────────
    def _limpiar(self):
        for w in self.winfo_children():
            w.destroy()

    def on_closing(self):
        if self.conexion:
            self.conexion.desconectar()
        self.destroy()


# ──────────────────────────────────────────────
#  ENTRADA
# ──────────────────────────────────────────────
if __name__ == "__main__":
    app = AppChat()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()