"""
Servidor Web para Chat en Azure sin dependencias externas
"""
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
import sqlite3
import bcrypt
import os
import atexit
import signal
from datetime import datetime
import threading
import secrets

app = Flask(__name__)
# Usar variable de entorno en Azure, o generar una aleatoria
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
async_mode = 'eventlet' if 'WEBSITE_HOSTNAME' in os.environ else 'threading'
socketio = SocketIO(app, cors_allowed_origins="*",
                    async_mode=async_mode,
                    ping_timeout=60,
                    ping_interval=25,
                    max_http_buffer_size=10 * 1024 * 1024)

# Configuración de base de datos
DATABASE = '/home/site/wwwroot/database/chat.db' if 'WEBSITE_HOSTNAME' in os.environ else 'database/chat.db'

# Asegurar directorio de base de datos
os.makedirs(os.path.dirname(DATABASE) if os.path.dirname(DATABASE) else 'database', exist_ok=True)

# Usuarios conectados
usuarios_conectados = {}
usuarios_salas = {}

def init_db():
    """Inicializa la base de datos"""
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Tabla de usuarios
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Tabla de mensajes
    c.execute('''CREATE TABLE IF NOT EXISTS mensajes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user TEXT NOT NULL,
        to_user TEXT NOT NULL,
        contenido TEXT NOT NULL,
        timestamp REAL DEFAULT CURRENT_TIMESTAMP,
        leido INTEGER DEFAULT 0
    )''')
    
    # Tabla para archivos
    c.execute('''CREATE TABLE IF NOT EXISTS archivos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_user TEXT NOT NULL,
        to_user TEXT NOT NULL,
        nombre TEXT NOT NULL,
        tipo TEXT DEFAULT 'application/octet-stream',
        datos TEXT NOT NULL,
        timestamp REAL DEFAULT CURRENT_TIMESTAMP
    )''')

    # Migración: agregar columna tipo si la tabla ya existía sin ella
    try:
        c.execute("ALTER TABLE archivos ADD COLUMN tipo TEXT DEFAULT 'application/octet-stream'")
        conn.commit()
    except Exception:
        pass  # La columna ya existe
    
    conn.commit()
    conn.close()
    print("Base de datos inicializada (:")

def clear_db():
    """Limpia mensajes y archivos al cerrar el servidor (los usuarios se conservan)"""
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("DELETE FROM mensajes")
        c.execute("DELETE FROM archivos")
        conn.commit()
        conn.close()
        print("Mensajes limpiados al cerrar el servidor")
    except Exception as e:
        print(f"Error al limpiar mensajes: {e}")

def _signal_handler(*_):
    clear_db()
    os._exit(0)

atexit.register(clear_db)
signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)

def get_db():
    """Obtiene conexión a la base de datos"""
    return sqlite3.connect(DATABASE)

@app.route('/')
def index():
    """Página principal"""
    return render_template('index.html')

@app.route('/health')
def health():
    """Endpoint para health check de Azure"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200

@app.route('/api/register', methods=['POST'])
def register():
    """Registro de usuario"""
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    
    if not username or not password:
        return jsonify({'error': 'Usuario y contraseña requeridos'}), 400
    
    if len(username) < 3:
        return jsonify({'error': 'El usuario debe tener al menos 3 caracteres'}), 400
    
    if len(password) < 4:
        return jsonify({'error': 'La contraseña debe tener al menos 4 caracteres'}), 400
    
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO usuarios (username, password) VALUES (?, ?)", 
                  (username, hashed))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Usuario registrado'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'El usuario ya existe'}), 400

@app.route('/api/login', methods=['POST'])
def login():
    """Inicio de sesión"""
    data = request.json
    username = data.get('username', '').strip().lower()
    password = data.get('password', '').strip()
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT password FROM usuarios WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    
    if result and bcrypt.checkpw(password.encode('utf-8'), result[0]):
        session['username'] = username
        return jsonify({'success': True, 'username': username})
    
    return jsonify({'error': 'Usuario o contraseña incorrectos'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    """Cierre de sesión"""
    username = session.get('username')
    if username and username in usuarios_conectados:
        # Buscar y eliminar el socket_id del usuario
        for sid, user in list(usuarios_conectados.items()):
            if user == username:
                del usuarios_conectados[sid]
                break
    
    session.pop('username', None)
    return jsonify({'success': True})

@app.route('/api/usuarios', methods=['GET'])
def get_usuarios():
    """Obtiene lista de usuarios"""
    if 'username' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    current_user = session['username']
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username FROM usuarios WHERE username != ?", (current_user,))
    usuarios = [row[0] for row in c.fetchall()]
    conn.close()
    
    # Marcar quiénes están en línea
    usuarios_online = set(usuarios_conectados.values())
    
    return jsonify({
        'usuarios': usuarios,
        'online': list(usuarios_online)
    })

@app.route('/api/mensajes/<destino>', methods=['GET'])
def get_mensajes(destino):
    """Obtiene historial de mensajes"""
    if 'username' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    origen = session['username']
    destino = destino.lower()
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT from_user, contenido, timestamp 
                 FROM mensajes 
                 WHERE (from_user = ? AND to_user = ?) 
                    OR (from_user = ? AND to_user = ?)
                 ORDER BY timestamp ASC''',
              (origen, destino, destino, origen))
    
    mensajes = []
    for row in c.fetchall():
        mensajes.append({
            'from': row[0],
            'content': row[1],
            'time': row[2]
        })
    
    # Marcar mensajes como leídos
    c.execute('''UPDATE mensajes 
                 SET leido = 1 
                 WHERE from_user = ? AND to_user = ? AND leido = 0''',
              (destino, origen))
    conn.commit()
    conn.close()
    
    return jsonify({'mensajes': mensajes})

@app.route('/api/archivos/<destino>', methods=['GET'])
def get_archivos(destino):
    """Obtiene historial de archivos"""
    if 'username' not in session:
        return jsonify({'error': 'No autenticado'}), 401

    origen = session['username']
    destino = destino.lower()

    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT from_user, nombre, tipo, datos, timestamp
                 FROM archivos
                 WHERE (from_user = ? AND to_user = ?)
                    OR (from_user = ? AND to_user = ?)
                 ORDER BY timestamp ASC''',
              (origen, destino, destino, origen))

    archivos = []
    for row in c.fetchall():
        archivos.append({
            'from': row[0],
            'filename': row[1],
            'file_type': row[2] or 'application/octet-stream',
            'data': row[3],
            'time': row[4]
        })
    conn.close()

    return jsonify({'archivos': archivos})

@app.route('/api/mensajes/no_leidos', methods=['GET'])
def get_mensajes_no_leidos():
    """Obtiene mensajes no leídos"""
    if 'username' not in session:
        return jsonify({'error': 'No autenticado'}), 401
    
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT from_user, COUNT(*) 
                 FROM mensajes 
                 WHERE to_user = ? AND leido = 0
                 GROUP BY from_user''',
              (session['username'],))
    
    no_leidos = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    
    return jsonify({'no_leidos': no_leidos})

# WebSocket events
@socketio.on('connect')
def handle_connect():
    """Cliente conectado"""
    if 'username' in session:
        username = session['username']
        usuarios_conectados[request.sid] = username
        print(f"{username} conectado")
        
        # Notificar a todos
        emit('usuario_conectado', {'username': username}, broadcast=True)
        emit('usuarios_online', {'usuarios': list(set(usuarios_conectados.values()))}, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    """Cliente desconectado"""
    if request.sid in usuarios_conectados:
        username = usuarios_conectados[request.sid]
        del usuarios_conectados[request.sid]
        print(f"X {username} desconectado")
        emit('usuario_desconectado', {'username': username}, broadcast=True)
        emit('usuarios_online', {'usuarios': list(set(usuarios_conectados.values()))}, broadcast=True)

@socketio.on('join')
def handle_join(data):
    """Unirse a sala privada"""
    room = data['room']
    join_room(room)
    usuarios_salas[request.sid] = room

@socketio.on('private_message')
def handle_private_message(data):
    """Mensaje privado"""
    if 'username' not in session:
        return
    
    from_user = session['username']
    to_user = data['to'].lower()
    message = data['message'].strip()
    
    if not message:
        return
    
    # Guardar en base de datos
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO mensajes (from_user, to_user, contenido, timestamp)
                 VALUES (?, ?, ?, ?)''',
              (from_user, to_user, message, datetime.now().timestamp()))
    conn.commit()
    conn.close()
    
    # Enviar en tiempo real
    room = f"chat_{min(from_user, to_user)}_{max(from_user, to_user)}"
    emit('new_message', {
        'from': from_user,
        'to': to_user,
        'content': message,
        'time': datetime.now().strftime('%H:%M')
    }, room=room)
    
    # Notificar al destinatario si está conectado
    for sid, user in usuarios_conectados.items():
        if user == to_user:
            emit('mensaje_recibido', {
                'from': from_user,
                'message': message
            }, room=sid)
            break

@socketio.on('send_file')
def handle_send_file(data):
    """Recibe y distribuye un archivo"""
    if 'username' not in session:
        return

    from_user = session['username']
    to_user = data['to'].lower()
    filename = data.get('filename', 'archivo')
    file_data = data.get('data', '')
    file_type = data.get('file_type', 'application/octet-stream')

    if not file_data:
        return

    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO archivos (from_user, to_user, nombre, tipo, datos, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (from_user, to_user, filename, file_type, file_data, datetime.now().timestamp()))
    conn.commit()
    conn.close()

    room = f"chat_{min(from_user, to_user)}_{max(from_user, to_user)}"
    emit('new_file', {
        'from': from_user,
        'to': to_user,
        'filename': filename,
        'data': file_data,
        'file_type': file_type,
        'time': datetime.now().strftime('%H:%M')
    }, room=room)

if __name__ == '__main__':
    init_db()
    print("=" * 50)
    print("Servidor ChatLamport Iniciado")
    print(f"Base de datos: {DATABASE}")
    print("Puerto: 8000")
    print("=" * 50)
    
    # Usando puerto 8000 al agregarlo dentro del server
    port = int(os.environ.get('PORT', 8000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)