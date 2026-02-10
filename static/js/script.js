// Global Variables
let currentSessionId = null;
let currentMode = 'chat';
let abortController = null; // To stop generation

// Initialize
document.addEventListener("DOMContentLoaded", () => {
    loadHistory();
    createNewChat(); // Start fresh
});

// --- CORE FUNCTIONS ---

async function createNewChat() {
    try {
        const res = await fetch('/api/new_chat');
        const data = await res.json();
        currentSessionId = data.session_id;
        
        // UI Reset: Show Welcome Screen
        const chatBox = document.getElementById('chat-box');
        chatBox.innerHTML = `
            <div id="welcome-screen" class="flex flex-col items-center justify-center h-full opacity-60 text-center">
                <div class="w-20 h-20 rounded-full bg-gradient-to-tr from-pink-500 to-purple-600 flex items-center justify-center text-4xl mb-4 shadow-2xl">🌸</div>
                <h2 class="text-2xl font-bold">Namaste!</h2>
                <p>Select a mode below to start.</p>
            </div>`;
        loadHistory();
    } catch (e) { console.error(e); }
}

// 👇 UPDATED SEND MESSAGE FUNCTION
async function sendMessage() {
    const inputField = document.getElementById('user-input');
    const sendBtnIcon = document.querySelector('button[type="submit"] i');
    const welcomeScreen = document.getElementById('welcome-screen');
    const message = inputField.value.trim();

    // 🛑 STOP LOGIC
    if (abortController) {
        abortController.abort();
        abortController = null;
        
        // Remove Loader
        const loader = document.getElementById("loading-bubble");
        if(loader) loader.remove();
        
        sendBtnIcon.className = "fas fa-arrow-up";
        sendBtnIcon.parentElement.classList.remove("bg-red-500");
        appendMessage('shanvika', "🛑 *Stopped by user.*");
        return;
    }

    if (!message) return;

    // 1. Hide Welcome Screen (Jadoo 🪄)
    if (welcomeScreen) welcomeScreen.style.display = 'none';

    // 2. Show User Message
    appendMessage('user', message);
    inputField.value = '';

    // 3. Start Loading UI
    abortController = new AbortController();
    sendBtnIcon.className = "fas fa-stop";
    sendBtnIcon.parentElement.classList.add("bg-red-500");

    // 👇 ADD LOADING BUBBLE TO CHAT
    const chatBox = document.getElementById('chat-box');
    const loadingDiv = document.createElement('div');
    loadingDiv.id = "loading-bubble";
    loadingDiv.className = "p-4 mb-4 rounded-2xl bg-gray-800 w-fit mr-auto border border-gray-700 flex items-center gap-2";
    
    let statusText = "Thinking";
    if (currentMode === 'coding') statusText = "Coding";
    else if (currentMode === 'image_gen') statusText = "Creating";
    
    loadingDiv.innerHTML = `<i class="fas fa-robot text-pink-500"></i> <span class="text-gray-400 text-sm">${statusText}</span> <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>`;
    chatBox.appendChild(loadingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                message: message, 
                session_id: currentSessionId, 
                mode: currentMode 
            }),
            signal: abortController.signal
        });

        const data = await response.json();

        // Remove Loader
        const currentLoader = document.getElementById("loading-bubble");
        if (currentLoader) currentLoader.remove();

        if (data.reply) {
            appendMessage('shanvika', data.reply);
        } else {
            appendMessage('shanvika', "⚠️ Empty response.");
        }

    } catch (error) {
        // Remove Loader on Error
        const currentLoader = document.getElementById("loading-bubble");
        if (currentLoader) currentLoader.remove();

        // ⚠️ FIX: Ignore 'AbortError' (Don't show "Could not connect")
        if (error.name !== 'AbortError') {
            console.error(error);
            appendMessage('shanvika', "⚠️ Server Error. Please try again.");
        }
    } finally {
        abortController = null;
        sendBtnIcon.className = "fas fa-arrow-up";
        sendBtnIcon.parentElement.classList.remove("bg-red-500");
    }
}

// 👇 UPDATED APPEND MESSAGE (Better Styling)
function appendMessage(sender, text) {
    const chatBox = document.getElementById('chat-box');
    const msgDiv = document.createElement('div');
    
    if (sender === 'user') {
        msgDiv.className = "p-3 mb-4 rounded-2xl bg-blue-600 text-white w-fit max-w-[85%] ml-auto break-words shadow-lg";
        msgDiv.innerText = text;
    } else {
        msgDiv.className = "p-4 mb-4 rounded-2xl bg-gray-800 text-gray-200 w-fit max-w-[85%] mr-auto break-words border border-gray-700 shadow-lg";
        msgDiv.innerHTML = marked.parse(text);
        msgDiv.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
        
        // Copy Button
        msgDiv.querySelectorAll('pre').forEach((pre) => {
            const btn = document.createElement('button');
            btn.className = 'copy-btn';
            btn.innerHTML = '<i class="fas fa-copy"></i> Copy';
            btn.addEventListener('click', () => {
                const code = pre.querySelector('code').innerText;
                navigator.clipboard.writeText(code);
                btn.innerHTML = '<i class="fas fa-check"></i>';
                setTimeout(() => btn.innerHTML = '<i class="fas fa-copy"></i> Copy', 2000);
            });
            pre.appendChild(btn);
        });
    }

    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// ... (Baaki functions same rahenge: setMode, loadHistory etc.) ...
// Agar purane functions copy karne mein dikkat ho, to bata dena main puri file de dunga.
// Filhal upar wala part replace karna zaroori hai.

function setMode(mode, btn) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(b => {
        b.classList.remove('active', 'bg-gradient-to-r', 'from-pink-500', 'to-purple-600', 'text-white', 'border-none');
        b.classList.add('bg-white/10', 'text-gray-300', 'border', 'border-white/10');
    });
    btn.classList.remove('bg-white/10', 'text-gray-300', 'border', 'border-white/10');
    btn.classList.add('active', 'bg-gradient-to-r', 'from-pink-500', 'to-purple-600', 'text-white', 'border-none');
}

async function loadHistory() {
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        const list = document.getElementById('history-list');
        list.innerHTML = '';
        data.history.forEach(chat => {
            const div = document.createElement('div');
            div.className = "p-3 hover:bg-white/5 rounded-lg cursor-pointer text-sm text-gray-300 truncate";
            div.innerText = chat.title;
            div.onclick = () => loadChat(chat.id);
            list.appendChild(div);
        });
    } catch (e) {}
}

async function loadChat(sid) {
    currentSessionId = sid;
    const chatBox = document.getElementById('chat-box');
    chatBox.innerHTML = ''; // Clear current
    
    // Hide welcome screen when loading a chat
    const welcomeScreen = document.getElementById('welcome-screen');
    if (welcomeScreen) welcomeScreen.style.display = 'none';

    const res = await fetch(`/api/chat/${sid}`);
    const data = await res.json();
    
    data.messages.forEach(msg => {
        appendMessage(msg.role === 'user' ? 'user' : 'shanvika', msg.content);
    });
}

function openSettingsModal() { document.getElementById('settings-modal').style.display = 'block'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }
function toggleTheme() { document.body.classList.toggle('light-mode'); document.body.classList.toggle('dark-mode'); }