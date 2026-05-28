function agregarMensaje(texto, tipo) {
    const zonaMensajes = document.getElementById("mensajes");

    const nuevoMensaje = document.createElement("div");
    nuevoMensaje.classList.add("mensaje");
    nuevoMensaje.classList.add(tipo);
    nuevoMensaje.textContent = texto;

    zonaMensajes.appendChild(nuevoMensaje);
    zonaMensajes.scrollTop = zonaMensajes.scrollHeight;
}

function enviarMensaje() {
    const entrada = document.getElementById("entradaMensaje");
    const mensaje = entrada.value.trim();

    if (mensaje === "") {
        return;
    }

    agregarMensaje(mensaje, "usuario");
    entrada.value = "";

    fetch("/enviar", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ mensaje: mensaje })
    })
    .then(response => response.json())
    .then(data => {
        agregarMensaje(data.respuesta, "servidor");
    })
    .catch(error => {
        agregarMensaje("Error al conectar con Flask.", "servidor");
        console.error(error);
    });
}

document.getElementById("entradaMensaje").addEventListener("keydown", function(event) {
    if (event.key === "Enter") {
        enviarMensaje();
    }
});