// Estado de la aplicación
let socket = null;
let currentUser = null;
let currentChat = null;
let usuariosOnline = new Set();

// Elementos DOM
const loginOverlay = document.getElementById('loginOverlay');
const sidebar = document.getElementById('sidebar');
const chatMain = document.getElementById('chatMain');
const usernameInput = document.getElementById('username');
const passwordInput = document.getElementById('password');
const btnLogin = document.getElementById('btnLogin');
const toggleMode = document.getElementById('toggleMode');
const errorMsg = document.getElementById('errorMsg');
const btnLogout = document.getElementById('btnLogout');
const currentUserSpan = document.getElementById('currentUser');
const userAvatar = document.getElementById('userAvatar');
const usersListDiv = document.getElementById('usersList');
const chatWithSpan = document.getElementById('chatWith');
const chatStatusSpan = document.getElementById('chatStatus');
const chatAvatar = document.getElementById('chatAvatar');
const messagesDiv = document.getElementById('messages');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');

let isLoginMode = true;

// Mostrar error
function showError(msg) {
  errorMsg.textContent = msg;
  setTimeout(() => { errorMsg.textContent = ''; }, 3000);
}

// Cambiar entre login y registro
toggleMode.addEventListener('click', () => {
  isLoginMode = !isLoginMode;
  if (isLoginMode) {
    toggleMode.textContent = '¿No tienes cuenta? Regístrate';
    btnLogin.textContent = 'Iniciar Sesión';
  } else {
    toggleMode.textContent = '¿Ya tienes cuenta? Inicia Sesión';
    btnLogin.textContent = 'Registrarse';
  }
});

// Login/Registro
btnLogin.addEventListener('click', async () => {
  const username = usernameInput.value.trim();
  const password = passwordInput.value.trim();
  
  if (!username || !password) {
    showError('Completa todos los campos');
    return;
  }
  
  const endpoint = isLoginMode ? '/api/login' : '/api/register';
  
  try {
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    
    const data = await response.json();
    
    if (response.ok) {
      if (isLoginMode) {
        // Inicio de sesión exitoso
        currentUser = data.username;
        currentUserSpan.textContent = currentUser;
        userAvatar.textContent = currentUser[0].toUpperCase();
        
        // Mostrar interfaz de chat
        loginOverlay.style.display = 'none';
        sidebar.style.display = 'flex';
        chatMain.style.display = 'flex';
        
        // Conectar WebSocket
        connectSocket();
        
        // Cargar usuarios
        loadUsers();
      } else {
        // Registro exitoso, cambiar a modo login
        showError('Usuario registrado. Inicia sesión.');
        isLoginMode = true;
        toggleMode.textContent = '¿No tienes cuenta? Regístrate';
        btnLogin.textContent = 'Iniciar Sesión';
        usernameInput.value = '';
        passwordInput.value = '';
      }
    } else {
      showError(data.error || 'Error');
    }
  } catch (err) {
    showError('Error de conexión');
  }
});

// Cerrar sesión
btnLogout.addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST' });
  if (socket) socket.disconnect();
  location.reload();
});

// Conectar WebSocket
function connectSocket() {
  socket = io();
  
  socket.on('connect', () => {
    console.log('Conectado al servidor WebSocket');
  });
  
  socket.on('usuarios_online', (data) => {
    usuariosOnline = new Set(data.usuarios);
    updateUserList();
  });
  
  socket.on('usuario_conectado', (data) => {
    usuariosOnline.add(data.username);
    updateUserList();
    addSystemMessage(`${data.username} se ha conectado`);
  });
  
  socket.on('usuario_desconectado', (data) => {
    usuariosOnline.delete(data.username);
    updateUserList();
    addSystemMessage(`${data.username} se ha desconectado`);
  });
  
  socket.on('new_message', (data) => {
    if (currentChat === data.from || currentChat === data.to) {
      addMessageToChat(data.from, data.content, data.time, data.from === currentUser);
    }
    // Actualizar contador de mensajes no leídos
    updateUnreadCount();
  });
  
  socket.on('mensaje_recibido', (data) => {
    if (currentChat !== data.from) {
      updateUnreadCount();
    }
  });
}

// Cargar lista de usuarios
async function loadUsers() {
  try {
    const response = await fetch('/api/usuarios');
    const data = await response.json();
    renderUsersList(data.usuarios);
  } catch (err) {
    console.error('Error cargando usuarios:', err);
  }
}

// Renderizar lista de usuarios
function renderUsersList(usuarios) {
  usersListDiv.innerHTML = '';
  
  usuarios.forEach(usuario => {
    const isOnline = usuariosOnline.has(usuario);
    const chatItem = document.createElement('div');
    chatItem.className = 'chat-item';
    chatItem.onclick = () => selectChat(usuario);
    
    chatItem.innerHTML = `
      <div class="avatar ${isOnline ? 'avatar-blue' : 'avatar-purple'}" style="opacity: ${isOnline ? 1 : 0.6}">
        ${usuario[0].toUpperCase()}
      </div>
      <div class="chat-item-info">
        <div class="chat-item-top">
          <span class="chat-item-name">${usuario}</span>
          <span class="chat-item-time" id="time_${usuario}"></span>
        </div>
        <div class="chat-item-preview">
          <i class="ti ti-message" style="color: #5f7d96; font-size: 12px;"></i>
          <span class="chat-item-preview-text" id="preview_${usuario}">${isOnline ? 'En línea' : 'Offline'}</span>
        </div>
      </div>
    `;
    
    usersListDiv.appendChild(chatItem);
  });
}

function updateUserList() {
  loadUsers();
}

// Seleccionar chat
async function selectChat(username) {
  currentChat = username;
  chatWithSpan.textContent = username;
  chatAvatar.textContent = username[0].toUpperCase();
  
  const isOnline = usuariosOnline.has(username);
  chatStatusSpan.textContent = isOnline ? 'en línea' : 'offline';
  chatStatusSpan.style.color = isOnline ? '#2d8dc9' : '#5f7d96';
  
  // Habilitar input
  messageInput.disabled = false;
  sendBtn.disabled = false;
  
  // Unirse a la sala
  const room = `chat_${[currentUser, username].sort().join('_')}`;
  socket.emit('join', { room });
  
  // Cargar historial
  await loadChatHistory(username);
}

// Cargar historial de mensajes
async function loadChatHistory(username) {
  try {
    const response = await fetch(`/api/mensajes/${username}`);
    const data = await response.json();
    
    // Limpiar mensajes existentes (excepto separador de fecha)
    const dateSeparator = messagesDiv.querySelector('.date-separator');
    messagesDiv.innerHTML = '';
    if (dateSeparator) messagesDiv.appendChild(dateSeparator.cloneNode(true));
    else messagesDiv.innerHTML = '<div class="date-separator"><span>Historial</span></div>';
    
    data.mensajes.forEach(msg => {
      addMessageToChat(msg.from, msg.content, formatTime(msg.time), msg.from === currentUser);
    });
    
    scrollToBottom();
  } catch (err) {
    console.error('Error cargando historial:', err);
  }
}

// Agregar mensaje al chat
function addMessageToChat(sender, content, time, isSent) {
  const bubbleRow = document.createElement('div');
  bubbleRow.className = `bubble-row ${isSent ? 'sent' : 'received'}`;
  
  bubbleRow.innerHTML = `
    <div class="bubble ${isSent ? 'sent' : 'received'}">
      ${!isSent ? `<div class="bubble-sender">${sender}</div>` : ''}
      <div class="bubble-text">${escapeHtml(content)}</div>
      <div class="bubble-meta">
        <span class="bubble-time">${time}</span>
        ${isSent ? '<i class="ti ti-checks check-icon"></i>' : ''}
      </div>
    </div>
  `;
  
  messagesDiv.appendChild(bubbleRow);
  scrollToBottom();
}

function addSystemMessage(message) {
  const sysMsg = document.createElement('div');
  sysMsg.style.textAlign = 'center';
  sysMsg.style.color = '#5f7d96';
  sysMsg.style.fontSize = '12px';
  sysMsg.style.margin = '8px 0';
  sysMsg.textContent = message;
  messagesDiv.appendChild(sysMsg);
  scrollToBottom();
}

// Enviar mensaje
async function sendMessage() {
  if (!currentChat || !messageInput.value.trim()) return;
  
  const message = messageInput.value.trim();
  const time = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
  
  // Mostrar localmente
  addMessageToChat(currentUser, message, time, true);
  
  // Enviar al servidor
  socket.emit('private_message', {
    to: currentChat,
    message: message
  });
  
  messageInput.value = '';
}

// Actualizar contador de mensajes no leídos
async function updateUnreadCount() {
  try {
    const response = await fetch('/api/mensajes/no_leidos');
    const data = await response.json();
    // Actualizar badges en la lista de usuarios
    // (implementación opcional)
  } catch (err) {}
}

// Utilidades
function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function formatTime(timestamp) {
  const date = new Date(timestamp * 1000);
  return date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
}

function scrollToBottom() {
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Event listeners
sendBtn.addEventListener('click', sendMessage);
messageInput.addEventListener('keypress', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Inicialización
console.log('ChatLamport listo');