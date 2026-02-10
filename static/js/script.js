let currentSessionId = null;
let currentMode = 'chat';
let abortController = null;
let currentFile = null;
let vantaEffect = null;

// 👇 START HERE
document.addEventListener("DOMContentLoaded", () => {
    loadHistory();
    loadProfile();
    initVanta();
    
    // Character count for settings
    const box = document.getElementById('custom-instruction-box');
    if(box) {
        box.addEventListener('input', function() {
            document.getElementById('char-count').innerText = `${this.value.length}/1000`;
        });
    }
});

// ==========================================
// ✨ VANTA BACKGROUND
// ==========================================
function initVanta() {
    if (vantaEffect) {
        vantaEffect.destroy();
        vantaEffect = null;
    }

    const isLight = document.body.classList.contains('light-mode');

    setTimeout(() => {
        try {
            if (isLight) {
                vantaEffect = VANTA.RINGS({ el: "#vanta-bg", mouseControls: true, touchControls: true, minHeight: 200.00, minWidth: 200.00, scale: 1.00, scaleMobile: 1.00, backgroundColor: 0xffffff, color: 0xec4899 });
            } else {
                vantaEffect = VANTA.HALO({ el: "#vanta-bg", mouseControls: true, touchControls: true, minHeight: 200.00, minWidth: 200.00, baseColor: 0xca2cac, backgroundColor: 0x000000, amplitudeFactor: 3.00, xOffset: -0.01, yOffset: 0.06, size: 1.40 });
            }
        } catch (e) { console.log("Vanta Init Error", e); }
    }, 100);
}

function toggleTheme() {
    document.body.classList.toggle('light-mode');
    initVanta();
}

// ==========================================
// 👤 PROFILE SYNC LOGIC
// ==========================================
async function loadProfile() {
    try {
        const res = await fetch('/api/profile');
        const data = await res.json();
        
        if (data.name) {
            const nameEl = document.getElementById('profile-name-sidebar');
            if(nameEl) nameEl.innerText = data.name;

            const imgEl = document.getElementById('profile-img-sidebar');
            const modalImg = document.getElementById('profile-img-modal');
            const imgSrc = data.avatar || `https://ui-avatars.com/api/?name=${data.name}&background=random&color=fff`;
            
            if(imgEl) imgEl.src = imgSrc;
            if(modalImg) modalImg.src = imgSrc;
            
            const inputEl = document.getElementById('profile-name-input');
            if(inputEl) inputEl.value = data.name;
        }
    } catch (e) {
        console.error("Profile load error:", e);
    }
}

// ==========================================
// 📁 FILE HANDLING
// ==========================================
async function handleFileUpload(input) {
    const file = input.files[0];
    if (!file) return;

    // Increased size limit for Converter (15MB)
    if (file.size > 15 * 1024 * 1024) {
        alert("File too large! Please upload under 15MB.");
        input.value = ""; return;
    }

    const sendBtn = document.querySelector('button[type="submit"]');
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin text-pink-500"></i>';
    
    const wrapper = document.querySelector('.input-wrapper');
    const oldPreview = document.getElementById('file-preview');
    if(oldPreview) oldPreview.remove();

    const previewDiv = document.createElement('div');
    previewDiv.id = "file-preview";
    previewDiv.className = "flex items-center gap-2 bg-gray-800 text-white px-3 py-2 rounded-lg mb-2 w-fit text-sm border border-gray-600 animate-pulse";
    
    let iconClass = 'fa-file-alt text-blue-400';
    if (file.type.includes('image')) iconClass = 'fa-image text-pink-400';
    else if (file.type.includes('pdf')) iconClass = 'fa-file-pdf text-red-400';
    else if (file.type.includes('word') || file.name.endsWith('.docx')) iconClass = 'fa-file-word text-blue-600';

    previewDiv.innerHTML = `<i class="fas ${iconClass}"></i> <span>${file.name}</span> <span class="text-xs text-gray-400 ml-2">(Processing...)</span>`;
    wrapper.insertBefore(previewDiv, wrapper.querySelector('.input-container'));

    try {
        const base64 = await toBase64(file);
        currentFile = { name: file.name, type: file.type, data: base64 };
        
        previewDiv.innerHTML = `
            <i class="fas ${iconClass}"></i> <span>${file.name}</span> 
            <span class="text-xs text-green-400 ml-2"><i class="fas fa-check"></i> Ready</span>
            <button onclick="clearFile()" class="text-gray-400 hover:text-white ml-2"><i class="fas fa-times"></i></button>
        `;
        previewDiv.classList.remove('animate-pulse');
    } catch (e) {
        alert("Error reading file"); clearFile();
    } finally {
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-arrow-up"></i>'; 
    }
}

function clearFile() {
    currentFile = null;
    const fileInput = document.getElementById('file-upload');
    if(fileInput) fileInput.value = "";
    const p = document.getElementById('file-preview');
    if(p) p.remove();
}

const toBase64 = file => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => resolve(reader.result);
    reader.onerror = error => reject(error);
});

// ==========================================
// 💬 CHAT LOGIC (BUG FIX HERE)
// ==========================================
async function createNewChat() {
    currentSessionId = null; 
    document.getElementById('chat-box').innerHTML = `
        <div id="welcome-screen" class="flex flex-col items-center justify-center h-full opacity-80 text-center animate-fade-in">
            <div class="w-24 h-24 rounded-full bg-gradient-to-tr from-pink-500 to-purple-600 flex items-center justify-center text-5xl mb-6 shadow-2xl">🌸</div>
            <h2 class="text-3xl font-bold mb-2">Namaste!</h2>
            <p class="text-gray-400">Main taiyaar hu. Aaj kya create karein?</p>
        </div>`;
    window.history.pushState({}, document.title, "/");
    clearFile(); // Clear file on new chat too
}

async function sendMessage() {
    const inputField = document.getElementById('user-input');
    const sendBtn = document.querySelector('button[type="submit"]');
    const sendBtnIcon = sendBtn.querySelector('i');
    const welcomeScreen = document.getElementById('welcome-screen');
    const message = inputField.value.trim();

    // 👇👇 BUG FIX: STOP BUTTON LOGIC 👇👇
    if (abortController) {
        abortController.abort();
        abortController = null;
        const loader = document.getElementById("loading-bubble");
        if(loader) loader.remove();
        
        sendBtnIcon.className = "fas fa-arrow-up";
        sendBtn.classList.remove("bg-red-500");
        
        // IMPORTANT: File ko yahan clear karna zaroori hai
        if(currentFile) {
            appendMessage('shanvika', `🛑 *Stopped.* (Cancelled attachment: ${currentFile.name})`);
            clearFile(); 
        } else {
            appendMessage('shanvika', "🛑 *Stopped.*");
        }
        return;
    }
    // 👆👆 BUG FIX END 👆👆

    if (!message && !currentFile) return;

    if (!currentSessionId) {
        try {
            const res = await fetch('/api/new_chat');
            const data = await res.json();
            currentSessionId = data.session_id;
            loadHistory(); 
        } catch (e) { return; }
    }

    if (welcomeScreen) welcomeScreen.style.display = 'none';
    
    let displayMsg = message;
    if (currentFile) displayMsg += ` <br><span class="text-xs text-gray-400 bg-gray-800 px-2 py-1 rounded mt-1 inline-block"><i class="fas fa-paperclip"></i> ${currentFile.name}</span>`;

    appendMessage('user', displayMsg);
    inputField.value = '';
    const p = document.getElementById('file-preview');
    if(p) p.style.display = 'none';

    abortController = new AbortController();
    sendBtnIcon.className = "fas fa-stop";
    sendBtn.classList.add("bg-red-500");

    // Dynamic Loading Text
    let loadingText = "Thinking...";
    if (currentMode === 'image_gen') loadingText = "🎨 Painting...";
    else if (currentMode === 'converter') loadingText = "🔄 Converting File...";
    else if (currentMode === 'anime') loadingText = "✨ Creating Anime...";
    else if (currentMode === 'research') loadingText = "🔍 Researching...";

    const chatBox = document.getElementById('chat-box');
    const loadingDiv = document.createElement('div');
    loadingDiv.id = "loading-bubble";
    loadingDiv.className = "p-4 mb-4 rounded-2xl bg-gray-800 w-fit mr-auto border border-gray-700 flex items-center gap-2 animate-fade-in";
    loadingDiv.innerHTML = `<i class="fas fa-robot text-pink-500"></i> <span class="text-gray-400 text-sm">${loadingText}</span> <div class="typing-dot"></div>`;
    chatBox.appendChild(loadingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const payload = { 
            message: message, session_id: currentSessionId, mode: currentMode,
            file_data: currentFile ? currentFile.data : null,
            file_type: currentFile ? currentFile.type : null
        };

        // Clear file immediately after sending request data
        clearFile();

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
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
        
        if (error.name === 'AbortError') {
            // Already handled in the stop logic block above
        } else {
            appendMessage('shanvika', "⚠️ Connection Error or Timeout.");
            console.error(error);
        }
    } finally {
        abortController = null;
        sendBtnIcon.className = "fas fa-arrow-up";
        sendBtn.classList.remove("bg-red-500");
        clearFile(); // Final safety clear
    }
}

function appendMessage(sender, text) {
    const chatBox = document.getElementById('chat-box');
    const msgDiv = document.createElement('div');
    
    if (sender === 'user') {
        msgDiv.className = "msg-user animate-fade-in";
        msgDiv.innerHTML = text; 
    } else {
        msgDiv.className = "msg-ai animate-fade-in";
        if (text.includes("<img") || text.includes("<video") || text.includes("<a href")) {
            msgDiv.innerHTML = text;
        } else {
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
    }
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// ==========================================
// 📜 HISTORY & UI
// ==========================================
async function loadHistory() {
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        const list = document.getElementById('history-list');
        list.innerHTML = '';
        
        data.history.forEach(chat => {
            const div = document.createElement('div');
            div.className = "p-3 mb-1 hover:bg-white/10 rounded-xl cursor-pointer text-sm text-gray-300 relative group flex items-center transition-all h-10";
            div.innerHTML = `
                <div class="w-10 flex justify-center shrink-0"><i class="fas fa-comment-alt text-gray-500 group-hover:text-pink-400 text-lg"></i></div>
                <span class="nav-label flex-1 truncate transition-opacity duration-200">${chat.title}</span> 
                <div class="w-8 flex justify-center nav-label"><i class="fas fa-ellipsis-v opacity-0 group-hover:opacity-100 text-gray-500 hover:text-white px-2" onclick="showDropdown(event, '${chat.id}')"></i></div>
            `;
            div.onclick = (e) => { if(!e.target.classList.contains('fa-ellipsis-v')) loadChat(chat.id); };
            list.appendChild(div);
        });
    } catch (e) {}
}

function showDropdown(event, sessionId) {
    event.stopPropagation();
    const menu = document.getElementById('dropdown');
    menu.style.top = `${event.clientY}px`; menu.style.left = `${event.clientX}px`; menu.classList.add('show');
    document.getElementById('act-delete').onclick = () => deleteChat(sessionId);
    document.getElementById('act-rename').onclick = () => renameChat(sessionId);
    document.addEventListener('click', () => menu.classList.remove('show'), { once: true });
}

async function deleteChat(sid) {
    if(!confirm("Delete?")) return;
    await fetch(`/api/delete_chat/${sid}`, { method: 'DELETE' });
    loadHistory(); if(currentSessionId === sid) createNewChat();
}

async function renameChat(sid) {
    const newName = prompt("New Name:");
    if(newName) {
        await fetch('/api/rename_chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ session_id: sid, new_title: newName }) });
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
    clearFile(); // Load chat karte waqt bhi file clear karo
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
function openProfileModal() { document.getElementById('profile-modal').style.display = 'block'; }
async function saveProfile() { closeModal('profile-modal'); }
async function saveInstructions() {
    const text = document.getElementById('custom-instruction-box').value;
    await fetch('/api/update_instructions', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ instruction: text }) });
    closeModal('settings-modal');
    alert("Instructions Saved!");
}