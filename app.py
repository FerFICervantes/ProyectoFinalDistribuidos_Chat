from flask import Flask, render_template, request, jsonify
from cliente_socket_web import enviar_mensaje_web

app = Flask(__name__)

@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/enviar", methods=["POST"])
def enviar():
    datos = request.get_json()

    destino = datos.get("destino", "SERVIDOR_CSHARP")
    mensaje = datos.get("mensaje", "")

    if mensaje.strip() == "":
        return jsonify({
            "estado": "error",
            "respuesta": "No puedes enviar un mensaje vacío."
        })

    print("Destino:", destino)
    print("Mensaje recibido desde la interfaz:", mensaje)

    respuesta = enviar_mensaje_web(destino, mensaje)

    return jsonify({
        "estado": "ok",
        "respuesta": respuesta
    })


if __name__ == "__main__":
    app.run(debug=True, port=8000)