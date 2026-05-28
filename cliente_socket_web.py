import socket
import time
import os

# IP del servidor C# :
HOST = "192.168.1.2"
PUERTO = 5000

NOMBRE_SERVIDOR = "SERVIDOR_CSHARP"

RUTA_BASE_ARCHIVOS = r"C:\Users\ferna\OneDrive\Documentos\FI UNAM CVMF\9no Sem\Sistemas Distribuidos\ProyectoFinal\ArchivosRecibidos"

reloj_lamport = 0
nombre_usuario = "Fer"


def incrementar_lamport():
    global reloj_lamport
    reloj_lamport += 1
    return reloj_lamport


def crear_carpeta_usuario(usuario):
    carpeta_usuario = os.path.join(RUTA_BASE_ARCHIVOS, usuario)
    os.makedirs(carpeta_usuario, exist_ok=True)
    return carpeta_usuario


def crear_mensaje_protocolo(tipo, origen, destino, contenido):
    lamport = incrementar_lamport()
    timestamp = int(time.time())
    vector = "{}"

    return f"{tipo}|{origen}|{destino}|{lamport}|{vector}|{timestamp}|{contenido}"


def crear_encabezado_archivo(origen, destino, nombre_archivo, tamano_archivo):
    lamport = incrementar_lamport()
    timestamp = int(time.time())
    vector = "{}"

    return f"FILE|{origen}|{destino}|{lamport}|{vector}|{timestamp}|{nombre_archivo}|{tamano_archivo}"


def enviar_linea(sock, linea):
    sock.sendall((linea + "\n").encode("utf-8"))


def leer_linea(sock):
    datos = b""

    while True:
        byte = sock.recv(1)

        if not byte:
            return None

        if byte == b"\n":
            break

        datos += byte

    return datos.decode("utf-8").rstrip("\r")


def conectar_cliente():
    cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    cliente.connect((HOST, PUERTO))
    return cliente


def enviar_login(usuario):
    cliente = conectar_cliente()

    mensaje_login = crear_mensaje_protocolo(
        "LOGIN",
        usuario,
        NOMBRE_SERVIDOR,
        usuario
    )

    enviar_linea(cliente, mensaje_login)
    cliente.close()


def enviar_mensaje_web(destino, contenido):
    try:
        cliente = conectar_cliente()

        mensaje = crear_mensaje_protocolo(
            "MSG",
            nombre_usuario,
            destino,
            contenido
        )

        enviar_linea(cliente, mensaje)

        respuesta = leer_linea(cliente)

        cliente.close()

        if respuesta:
            partes = respuesta.split("|")

            if len(partes) >= 7:
                return partes[6]

            return respuesta

        return "Mensaje enviado, pero no se recibió respuesta."

    except ConnectionRefusedError:
        return "No se pudo conectar con el servidor C#."

    except Exception as e:
        return f"Error al enviar mensaje: {e}"


def enviar_archivo_web(destino, ruta_archivo):
    try:
        if not os.path.exists(ruta_archivo):
            return "El archivo no existe."

        if not os.path.isfile(ruta_archivo):
            return "La ruta no corresponde a un archivo."

        cliente = conectar_cliente()

        nombre_archivo = os.path.basename(ruta_archivo)
        tamano_archivo = os.path.getsize(ruta_archivo)

        encabezado = crear_encabezado_archivo(
            nombre_usuario,
            destino,
            nombre_archivo,
            tamano_archivo
        )

        enviar_linea(cliente, encabezado)

        with open(ruta_archivo, "rb") as archivo:
            while True:
                bloque = archivo.read(1024)

                if not bloque:
                    break

                cliente.sendall(bloque)

        cliente.close()

        return f"Archivo enviado correctamente: {nombre_archivo}"

    except ConnectionRefusedError:
        return "No se pudo conectar con el servidor C#."

    except Exception as e:
        return f"Error al enviar archivo: {e}"