const input = document.querySelector('.input-field');
const sendBtn = document.querySelector('.send-btn');
const messages = document.querySelector('.messages');
const typingRow = document.querySelector('.typing-row');

function sendMessage() {
  const text = input.value.trim();
  if (!text) return;

  const now = new Date();
  const time = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');

  const row = document.createElement('div');
  row.className = 'bubble-row sent';
  row.innerHTML = `
    <div class="bubble sent">
      <div class="bubble-text">${escapeHtml(text)}</div>
      <div class="bubble-meta">
        <span class="bubble-time">${time}</span>
        <i class="ti ti-check check-icon" aria-hidden="true"></i>
      </div>
    </div>
  `;

  messages.insertBefore(row, typingRow);
  input.value = '';
  messages.scrollTop = messages.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

sendBtn.addEventListener('click', sendMessage);

input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

messages.scrollTop = messages.scrollHeight;
