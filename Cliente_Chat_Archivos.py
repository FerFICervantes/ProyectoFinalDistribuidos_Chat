import socket
import threading
import time
import os

# Si el servidor está en la misma máquina, usa 127.0.0.1
# Si está en otra computadora, cambia por la IPv4 de la máquina del servidor.
HOST = "192.168.1.2"
PUERTO = 5000

NOMBRE_SERVIDOR = "SERVIDOR_CSHARP"

# Ruta base donde se guardarán los archivos recibidos
RUTA_BASE_ARCHIVOS = r"C:\Users\ferna\OneDrive\Documentos\FI UNAM CVMF\9no Sem\Sistemas Distribuidos\ProyectoFinal\ArchivosRecibidos"

cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

reloj_lamport = 0
lock_lamport = threading.Lock()

nombre_usuario = ""


def incrementar_lamport():
    """
    Incrementa el reloj de Lamport antes de enviar un evento.
    """
    global reloj_lamport

    with lock_lamport:
        reloj_lamport += 1
        return reloj_lamport


def actualizar_lamport(lamport_recibido):
    """
    Actualiza el reloj de Lamport al recibir un evento.
    """
    global reloj_lamport

    with lock_lamport:
        reloj_lamport = max(reloj_lamport, lamport_recibido) + 1
        return reloj_lamport


def crear_carpeta_usuario(usuario):
    """
    Crea la carpeta del usuario dentro de la ruta base.
    """
    carpeta_usuario = os.path.join(RUTA_BASE_ARCHIVOS, usuario)
    os.makedirs(carpeta_usuario, exist_ok=True)
    return carpeta_usuario


def crear_mensaje_protocolo(tipo, origen, destino, contenido):
    """
    Crea un mensaje con formato:
    TIPO|ORIGEN|DESTINO|LAMPORT|VECTOR|TIMESTAMP|CONTENIDO
    """
    lamport = incrementar_lamport()
    timestamp = int(time.time())
    vector = "{}"

    return f"{tipo}|{origen}|{destino}|{lamport}|{vector}|{timestamp}|{contenido}"


def crear_encabezado_archivo(origen, destino, nombre_archivo, tamano_archivo):
    """
    Crea encabezado para enviar archivo:
    FILE|ORIGEN|DESTINO|LAMPORT|VECTOR|TIMESTAMP|NOMBRE_ARCHIVO|TAMAÑO
    """
    lamport = incrementar_lamport()
    timestamp = int(time.time())
    vector = "{}"

    return f"FILE|{origen}|{destino}|{lamport}|{vector}|{timestamp}|{nombre_archivo}|{tamano_archivo}"


def enviar_linea(linea):
    """
    Envía una línea terminada en salto de línea.
    """
    cliente.sendall((linea + "\n").encode("utf-8"))


def leer_linea(sock):
    """
    Lee datos del socket hasta encontrar salto de línea.
    """
    datos = b""

    while True:
        byte = sock.recv(1)

        if not byte:
            return None

        if byte == b"\n":
            break

        datos += byte

    return datos.decode("utf-8").rstrip("\r")


def leer_bytes_exactos(sock, cantidad):
    """
    Lee exactamente la cantidad de bytes esperada.
    """
    datos = b""

    while len(datos) < cantidad:
        paquete = sock.recv(cantidad - len(datos))

        if not paquete:
            raise ConnectionError("La conexión se cerró mientras se recibía el archivo.")

        datos += paquete

    return datos


def enviar_login():
    """
    Envía el usuario al servidor.
    """
    mensaje_login = crear_mensaje_protocolo(
        "LOGIN",
        nombre_usuario,
        NOMBRE_SERVIDOR,
        nombre_usuario
    )

    enviar_linea(mensaje_login)


def procesar_mensaje(partes):
    """
    Procesa mensajes normales y ACK.
    """
    tipo = partes[0]
    origen = partes[1]
    destino = partes[2]
    lamport_recibido = int(partes[3])
    contenido = partes[6]

    lamport_actual = actualizar_lamport(lamport_recibido)

    if tipo == "ACK":
        print(f"\n[SERVIDOR] {contenido}")
    else:
        print(f"\n[{origen} → {destino}] {contenido}")

    print(f"Lamport recibido: {lamport_recibido}")
    print(f"Lamport local actualizado: {lamport_actual}")
    print("Tú: ", end="")


def procesar_archivo(partes):
    """
    Recibe un archivo, lo guarda en la carpeta del usuario actual
    y conserva el nombre del usuario que lo mandó.
    """
    origen = partes[1]
    destino = partes[2]
    lamport_recibido = int(partes[3])
    nombre_archivo = os.path.basename(partes[6])
    tamano_archivo = int(partes[7])

    lamport_actual = actualizar_lamport(lamport_recibido)

    print(f"\nRecibiendo archivo de {origen}")
    print(f"Destino: {destino}")
    print(f"Archivo: {nombre_archivo}")
    print(f"Tamaño: {tamano_archivo} bytes")

    bytes_archivo = leer_bytes_exactos(cliente, tamano_archivo)

    carpeta_usuario = crear_carpeta_usuario(nombre_usuario)

    ruta_destino = os.path.join(
        carpeta_usuario,
        f"{origen}_{nombre_archivo}"
    )

    with open(ruta_destino, "wb") as archivo:
        archivo.write(bytes_archivo)

    print(f"Archivo guardado correctamente en: {ruta_destino}")
    print(f"Lamport recibido: {lamport_recibido}")
    print(f"Lamport local actualizado: {lamport_actual}")
    print("Tú: ", end="")


def recibir_datos():
    """
    Hilo que recibe mensajes y archivos del servidor.
    """
    while True:
        try:
            encabezado = leer_linea(cliente)

            if encabezado is None:
                print("\nEl servidor cerró la conexión.")
                break

            partes = encabezado.split("|")

            if len(partes) < 7:
                print(f"\nEncabezado inválido: {encabezado}")
                continue

            tipo = partes[0]

            if tipo == "MSG" or tipo == "ACK":
                procesar_mensaje(partes)

            elif tipo == "FILE":
                if len(partes) < 8:
                    print("\nEncabezado FILE inválido.")
                    continue

                procesar_archivo(partes)

            else:
                print(f"\nTipo de paquete no reconocido: {tipo}")

        except Exception as e:
            print(f"\nError al recibir datos: {e}")
            break


def enviar_mensaje():
    """
    Envía un mensaje privado, al servidor o a todos.
    """
    print("\nEjemplos de destino:")
    print("- Alonso")
    print("- Fernanda")
    print("- Maria")
    print("- SERVIDOR_CSHARP")
    print("- BROADCAST")

    destino = input("Destino: ")
    contenido = input("Mensaje: ")

    if not destino or not contenido:
        print("Datos inválidos.")
        return

    mensaje = crear_mensaje_protocolo(
        "MSG",
        nombre_usuario,
        destino,
        contenido
    )

    enviar_linea(mensaje)


def enviar_archivo():
    """
    Envía un archivo al servidor, a un usuario o a todos.
    """
    print("\nEjemplos de destino:")
    print("- Alonso")
    print("- Fernanda")
    print("- Maria")
    print("- SERVIDOR_CSHARP")
    print("- BROADCAST")

    destino = input("Destino: ")
    ruta_archivo = input("Ruta completa del archivo: ")

    if not destino or not ruta_archivo:
        print("Datos inválidos.")
        return

    if not os.path.exists(ruta_archivo):
        print("El archivo no existe.")
        return

    if not os.path.isfile(ruta_archivo):
        print("La ruta no corresponde a un archivo.")
        return

    nombre_archivo = os.path.basename(ruta_archivo)
    tamano_archivo = os.path.getsize(ruta_archivo)

    encabezado = crear_encabezado_archivo(
        nombre_usuario,
        destino,
        nombre_archivo,
        tamano_archivo
    )

    try:
        enviar_linea(encabezado)

        with open(ruta_archivo, "rb") as archivo:
            while True:
                bloque = archivo.read(1024)

                if not bloque:
                    break

                cliente.sendall(bloque)

        print(f"Archivo enviado correctamente: {nombre_archivo}")

    except Exception as e:
        print(f"Error al enviar archivo: {e}")


def menu_cliente():
    """
    Menú principal del cliente.
    """
    while True:
        print("\n====== MENÚ CLIENTE ======")
        print("1. Enviar mensaje")
        print("2. Enviar archivo")
        print("3. Salir")
        print("==========================")

        opcion = input("Opción: ")

        if opcion == "1":
            enviar_mensaje()

        elif opcion == "2":
            enviar_archivo()

        elif opcion == "3":
            print("Cerrando cliente...")
            cliente.close()
            break

        else:
            print("Opción inválida.")


def main():
    global nombre_usuario

    nombre_usuario = input("Ingresa tu nombre de usuario: ")

    crear_carpeta_usuario(nombre_usuario)

    try:
        cliente.connect((HOST, PUERTO))

        print("Conectado al servidor C#.")
        print(f"Ruta de archivos recibidos: {RUTA_BASE_ARCHIVOS}")
        print("Enviando LOGIN...\n")

        enviar_login()

        hilo_recepcion = threading.Thread(target=recibir_datos)
        hilo_recepcion.daemon = True
        hilo_recepcion.start()

        menu_cliente()

    except ConnectionRefusedError:
        print("No se pudo conectar. Verifica que el servidor esté encendido.")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()