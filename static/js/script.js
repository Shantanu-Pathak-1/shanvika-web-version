let currentSessionId = null;
let currentMode = 'chat';
let abortController = null;
let currentFile = null; // Store uploaded file data

// 👇 ON LOAD
document.addEventListener("DOMContentLoaded", () => {
    loadHistory();
    
    // Character Counter for Settings
    const box = document.getElementById('custom-instruction-box');
    if(box) {
        box.addEventListener('input', function() {
            document.getElementById('char-count').innerText = `${this.value.length}/1000`;
        });
    }
});

// ==========================================
// 📁 FILE HANDLING LOGIC (NEW)
// ==========================================

async function handleFileUpload(input) {
    const file = input.files[0];
    if (!file) return;

    // 5MB Limit check
    if (file.size > 5 * 1024 * 1024) {
        alert("File too large! Please upload under 5MB.");
        input.value = ""; 
        return;
    }

    // Show Preview UI
    const wrapper = document.querySelector('.input-wrapper');
    const oldPreview = document.getElementById('file-preview');
    if(oldPreview) oldPreview.remove();

    const previewDiv = document.createElement('div');
    previewDiv.id = "file-preview";
    previewDiv.className = "flex items-center gap-2 bg-gray-800 text-white px-3 py-2 rounded-lg mb-2 w-fit text-sm border border-gray-600 animate-pulse";
    
    let iconClass = 'fa-file-alt text-blue-400';
    if (file.type.includes('image')) iconClass = 'fa-image text-pink-400';
    else if (file.type.includes('pdf')) iconClass = 'fa-file-pdf text-red-400';

    previewDiv.innerHTML = `
        <i class="fas ${iconClass}"></i>
        <span>${file.name}</span>
        <button onclick="clearFile()" class="text-gray-400 hover:text-white ml-2"><i class="fas fa-times"></i></button>
    `;
    wrapper.insertBefore(previewDiv, wrapper.querySelector('.input-container'));

    // Convert to Base64 for Backend
    try {
        const base64 = await toBase64(file);
        currentFile = {
            name: file.name,
            type: file.type,
            data: base64 
        };
    } catch (e) {
        alert("Error reading file");
        clearFile();
    }
}

function clearFile() {
    currentFile = null;
    document.getElementById('file-upload').value = "";
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
// 💬 CHAT LOGIC
// ==========================================

async function createNewChat() {
    currentSessionId = null; 
    document.getElementById('chat-box').innerHTML = `
        <div id="welcome-screen" class="flex flex-col items-center justify-center h-full opacity-60 text-center">
            <div class="w-20 h-20 rounded-full bg-gradient-to-tr from-pink-500 to-purple-600 flex items-center justify-center text-4xl mb-4 shadow-2xl">🌸</div>
            <h2 class="text-2xl font-bold">Namaste!</h2>
            <p>Select a mode below to start.</p>
        </div>`;
    // URL clean karo
    window.history.pushState({}, document.title, "/");
}

async function sendMessage() {
    const inputField = document.getElementById('user-input');
    const sendBtnIcon = document.querySelector('button[type="submit"] i');
    const welcomeScreen = document.getElementById('welcome-screen');
    const message = inputField.value.trim();

    // STOP GENERATION LOGIC
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

    // Empty check (Agar file nahi hai aur text bhi nahi hai toh return)
    if (!message && !currentFile) return;

    // Create Session if not exists
    if (!currentSessionId) {
        try {
            const res = await fetch('/api/new_chat');
            const data = await res.json();
            currentSessionId = data.session_id;
            loadHistory(); 
        } catch (e) { return; }
    }

    if (welcomeScreen) welcomeScreen.style.display = 'none';
    
    // UI Display Logic
    let displayMsg = message;
    if (currentFile) {
        displayMsg += ` <br><span class="text-xs text-gray-400 bg-gray-800 px-2 py-1 rounded mt-1 inline-block"><i class="fas fa-paperclip"></i> ${currentFile.name}</span>`;
    }

    appendMessage('user', displayMsg);
    inputField.value = '';
    
    // Hide Preview
    const p = document.getElementById('file-preview');
    if(p) p.style.display = 'none';

    // Loading State
    abortController = new AbortController();
    sendBtnIcon.className = "fas fa-stop";
    sendBtnIcon.parentElement.classList.add("bg-red-500");

    const chatBox = document.getElementById('chat-box');
    const loadingDiv = document.createElement('div');
    loadingDiv.id = "loading-bubble";
    loadingDiv.className = "p-4 mb-4 rounded-2xl bg-gray-800 w-fit mr-auto border border-gray-700 flex items-center gap-2";
    
    let statusText = "Thinking";
    if (currentMode === 'coding') statusText = "Coding";
    else if (currentMode === 'image_gen') statusText = "Painting";
    else if (currentMode === 'video') statusText = "Filming";
    
    loadingDiv.innerHTML = `<i class="fas fa-robot text-pink-500"></i> <span class="text-gray-400 text-sm">${statusText}...</span> <div class="typing-dot"></div>`;
    chatBox.appendChild(loadingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        // Prepare Payload
        const payload = { 
            message: message, 
            session_id: currentSessionId, 
            mode: currentMode,
            file_data: currentFile ? currentFile.data : null,
            file_type: currentFile ? currentFile.type : null
        };

        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: abortController.signal
        });

        // Clear file from memory after sending
        clearFile();

        const data = await response.json();
        const currentLoader = document.getElementById("loading-bubble");
        if (currentLoader) currentLoader.remove();

        if (data.reply) appendMessage('shanvika', data.reply);
        else appendMessage('shanvika', "⚠️ Empty response.");

    } catch (error) {
        const currentLoader = document.getElementById("loading-bubble");
        if (currentLoader) currentLoader.remove();
        if (error.name !== 'AbortError') appendMessage('shanvika', "⚠️ Connection Error.");
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
        // User message treated as HTML to show file icon
        msgDiv.innerHTML = text; 
    } else {
        msgDiv.className = "msg-ai p-4 mb-4 rounded-2xl w-fit max-w-[85%] mr-auto break-words shadow-lg bg-gray-800 border border-gray-700 text-gray-200";
        
        // CHECK: If AI sends Image/Video HTML, inject directly
        if (text.includes("<img") || text.includes("<video")) {
            msgDiv.innerHTML = text;
        } else {
            // Otherwise use Markdown
            msgDiv.innerHTML = marked.parse(text);
            msgDiv.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
            
            // Copy Button Logic
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
// ⚙️ SETTINGS & PROFILE (FIXED)
// ==========================================

// ✅ FIXED: Fetch data before opening modal
async function openSettingsModal() {
    document.getElementById('settings-modal').style.display = 'block';
    
    try {
        const res = await fetch('/api/profile');
        const data = await res.json();
        
        const box = document.getElementById('custom-instruction-box');
        if (data.custom_instruction) {
            box.value = data.custom_instruction;
            document.getElementById('char-count').innerText = `${data.custom_instruction.length}/1000`;
        } else {
            box.value = "";
            document.getElementById('char-count').innerText = "0/1000";
        }
    } catch (e) {
        console.error("Failed to load profile data", e);
    }
}

// ✅ FIXED: Save and give feedback
async function saveInstructions() {
    const txt = document.getElementById('custom-instruction-box').value;
    const btn = document.querySelector('#settings-modal button.text-pink-400');
    
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    
    try {
        await fetch('/api/update_instructions', { 
            method: 'POST', 
            headers: {'Content-Type': 'application/json'}, 
            body: JSON.stringify({ instruction: txt }) 
        });
        
        btn.innerHTML = '<i class="fas fa-check"></i> Saved!';
        setTimeout(() => {
            btn.innerHTML = originalText;
            closeModal('settings-modal');
        }, 1000);
        
    } catch (e) {
        alert("Error saving instructions");
        btn.innerHTML = originalText;
    }
}

function closeModal(id) { document.getElementById(id).style.display = 'none'; }
function toggleTheme() { document.body.classList.toggle('light-mode'); document.body.classList.toggle('dark-mode'); }

// Profile & Other Utils
function openProfileModal() { 
    document.getElementById('profile-modal').style.display = 'block'; 
    // Load current name
    fetch('/api/profile').then(r=>r.json()).then(d => {
        document.getElementById('profile-name-input').value = d.name;
        document.getElementById('profile-img-modal').src = d.avatar;
    });
}

async function saveProfile() { 
    const name = document.getElementById('profile-name-input').value;
    await fetch('/api/update_profile_name', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ name }) });
    closeModal('profile-modal');
    location.reload(); // Refresh to see changes
}

async function uploadAvatar(input) { 
    // Avatar logic remains skipped as it requires Cloudinary/S3 for Render
    alert("Avatar upload requires external storage (S3/Cloudinary) on Render.");
}

// ==========================================
// 📜 HISTORY & UTILS
// ==========================================

async function loadHistory() {
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        const list = document.getElementById('history-list');
        list.innerHTML = '';
        data.history.forEach(chat => {
            const div = document.createElement('div');
            div.className = "p-3 mb-1 hover:bg-white/5 rounded-xl cursor-pointer text-sm text-gray-300 relative group flex items-center gap-3 transition-all";
            div.innerHTML = `
                <i class="fas fa-comment-alt text-gray-500 group-hover:text-pink-400 text-lg shrink-0"></i> 
                <span class="nav-label flex-1 truncate">${chat.title}</span> 
                <i class="fas fa-ellipsis-v opacity-0 group-hover:opacity-100 text-gray-500 hover:text-white px-2 nav-label" onclick="showDropdown(event, '${chat.id}')"></i>
            `;
            // Click Handler
            div.onclick = (e) => { 
                if(!e.target.classList.contains('fa-ellipsis-v')) loadChat(chat.id); 
            };
            list.appendChild(div);
        });
    } catch (e) {}
}

function showDropdown(event, sessionId) {
    event.stopPropagation();
    const menu = document.getElementById('dropdown');
    menu.style.top = `${event.clientY}px`;
    menu.style.left = `${event.clientX}px`;
    menu.classList.add('show');
    
    document.getElementById('act-delete').onclick = () => deleteChat(sessionId);
    document.getElementById('act-rename').onclick = () => renameChat(sessionId);
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