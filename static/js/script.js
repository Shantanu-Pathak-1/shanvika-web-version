let currentSessionId = null;
let currentMode = 'chat';
let abortController = null;

// 👇 FIX: Start mein sirf history load karo, New Chat create mat karo
document.addEventListener("DOMContentLoaded", () => {
    loadHistory();
    // Default welcome screen dikhao, backend call mat karo abhi
});

// --- CORE FUNCTIONS ---

// User jab "New Chat" button dabaye, tabhi call hoga
async function createNewChat() {
    currentSessionId = null; // Reset ID
    // Clear Chat Box & Show Welcome Screen
    document.getElementById('chat-box').innerHTML = `
        <div id="welcome-screen" class="flex flex-col items-center justify-center h-full opacity-60 text-center">
            <div class="w-20 h-20 rounded-full bg-gradient-to-tr from-pink-500 to-purple-600 flex items-center justify-center text-4xl mb-4 shadow-2xl">🌸</div>
            <h2 class="text-2xl font-bold">Namaste!</h2>
            <p>Select a mode below to start.</p>
        </div>`;
    
    // URL se ID hatao
    window.history.pushState({}, document.title, "/");
}

async function sendMessage() {
    const inputField = document.getElementById('user-input');
    const sendBtnIcon = document.querySelector('button[type="submit"] i');
    const welcomeScreen = document.getElementById('welcome-screen');
    const message = inputField.value.trim();

    if (abortController) {
        abortController.abort();
        abortController = null;
        const loader = document.getElementById("loading-bubble");
        if(loader) loader.remove();
        sendBtnIcon.className = "fas fa-arrow-up";
        sendBtnIcon.parentElement.classList.remove("bg-red-500");
        appendMessage('shanvika', "🛑 *Stopped.*");
        return;
    }

    if (!message) return;

    // 👇 LOGIC FIX: Agar Session ID nahi hai, to pehle create karo
    if (!currentSessionId) {
        try {
            const res = await fetch('/api/new_chat');
            const data = await res.json();
            currentSessionId = data.session_id;
            loadHistory(); // List update karo
        } catch (e) {
            console.error("Failed to create session", e);
            return;
        }
    }

    if (welcomeScreen) welcomeScreen.style.display = 'none';
    appendMessage('user', message);
    inputField.value = '';

    // Start Loading
    abortController = new AbortController();
    sendBtnIcon.className = "fas fa-stop";
    sendBtnIcon.parentElement.classList.add("bg-red-500");

    // Add Loading Bubble
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
        const currentLoader = document.getElementById("loading-bubble");
        if (currentLoader) currentLoader.remove();

        if (data.reply) appendMessage('shanvika', data.reply);
        else appendMessage('shanvika', "⚠️ Empty response.");

    } catch (error) {
        const currentLoader = document.getElementById("loading-bubble");
        if (currentLoader) currentLoader.remove();
        if (error.name !== 'AbortError') appendMessage('shanvika', "⚠️ Error connecting.");
    } finally {
        abortController = null;
        sendBtnIcon.className = "fas fa-arrow-up";
        sendBtnIcon.parentElement.classList.remove("bg-red-500");
    }
}

function appendMessage(sender, text) {
    const chatBox = document.getElementById('chat-box');
    const msgDiv = document.createElement('div');
    
    if (sender === 'user') {
        msgDiv.className = "p-3 mb-4 rounded-2xl bg-blue-600 text-white w-fit max-w-[85%] ml-auto break-words shadow-lg";
        msgDiv.innerText = text;
    } else {
        msgDiv.className = "msg-ai p-4 mb-4 rounded-2xl w-fit max-w-[85%] mr-auto break-words shadow-lg";
        msgDiv.innerHTML = marked.parse(text);
        msgDiv.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
        
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

// --- HISTORY & DROPDOWN ---
async function loadHistory() {
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        const list = document.getElementById('history-list');
        list.innerHTML = '';
        data.history.forEach(chat => {
            const div = document.createElement('div');
            // 👇 Added Right Click Event
            div.className = "p-3 hover:bg-white/5 rounded-lg cursor-pointer text-sm text-gray-300 truncate relative group flex justify-between items-center";
            div.innerHTML = `<span>${chat.title}</span> <i class="fas fa-ellipsis-v opacity-0 group-hover:opacity-100 text-gray-500 hover:text-white px-2" onclick="showDropdown(event, '${chat.id}')"></i>`;
            div.onclick = (e) => { if(!e.target.classList.contains('fa-ellipsis-v')) loadChat(chat.id); };
            list.appendChild(div);
        });
    } catch (e) {}
}

// 👇 DROPDOWN LOGIC
function showDropdown(event, sessionId) {
    event.stopPropagation();
    const menu = document.getElementById('dropdown');
    menu.style.top = `${event.clientY}px`;
    menu.style.left = `${event.clientX}px`;
    menu.classList.add('show');
    
    // Setup actions
    document.getElementById('act-delete').onclick = () => deleteChat(sessionId);
    document.getElementById('act-rename').onclick = () => renameChat(sessionId);
    
    // Close on click elsewhere
    document.addEventListener('click', () => menu.classList.remove('show'), { once: true });
}

async function deleteChat(sid) {
    if(!confirm("Delete this chat?")) return;
    await fetch(`/api/delete_chat/${sid}`, { method: 'DELETE' });
    loadHistory();
    if(currentSessionId === sid) createNewChat();
}

async function renameChat(sid) {
    const newName = prompt("New Name:");
    if(newName) {
        await fetch('/api/rename_chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ session_id: sid, new_title: newName })
        });
        loadHistory();
    }
}

async function loadChat(sid) {
    currentSessionId = sid;
    const welcomeScreen = document.getElementById('welcome-screen');
    if (welcomeScreen) welcomeScreen.style.display = 'none';
    
    const chatBox = document.getElementById('chat-box');
    chatBox.innerHTML = ''; 
    
    const res = await fetch(`/api/chat/${sid}`);
    const data = await res.json();
    data.messages.forEach(msg => appendMessage(msg.role === 'user' ? 'user' : 'shanvika', msg.content));
}

function setMode(mode, btn) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(b => {
        b.classList.remove('active', 'bg-gradient-to-r', 'from-pink-500', 'to-purple-600', 'text-white', 'border-none');
        b.classList.add('bg-white/10', 'text-gray-300', 'border', 'border-white/10');
    });
    btn.classList.remove('bg-white/10', 'text-gray-300', 'border', 'border-white/10');
    btn.classList.add('active', 'bg-gradient-to-r', 'from-pink-500', 'to-purple-600', 'text-white', 'border-none');
}

// Utils
function openSettingsModal() { document.getElementById('settings-modal').style.display = 'block'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }
function toggleTheme() { document.body.classList.toggle('light-mode'); document.body.classList.toggle('dark-mode'); }
// Profile logic omitted for brevity, keep your existing profile logic