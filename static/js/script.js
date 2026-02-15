// ==================================================================================
//  FILE: static/js/script.js
//  DESCRIPTION: Main Frontend Logic for Shanvika AI (Chat, Voice, Tools, UI)
// ==================================================================================

let currentSessionId = localStorage.getItem('session_id') || null;
let currentMode = 'chat';
let isRecording = false;
let recognition = null;
let currentFile = null; // Store uploaded file data

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Background Animation
    if (window.VANTA) {
        VANTA.RINGS({
            el: "#vanta-bg",
            mouseControls: true,
            touchControls: true,
            gyroControls: false,
            minHeight: 200.00,
            minWidth: 200.00,
            scale: 1.00,
            scaleMobile: 1.00,
            backgroundColor: 0x000000,
            color: 0xec4899
        });
    }

    loadHistory();
    loadProfile();
    
    // Check for new chat
    if (!currentSessionId) createNewChat();
    else loadChat(currentSessionId);
    
    // Restore Theme
    if (localStorage.getItem('theme') === 'light') document.body.classList.add('light-mode');
});

// --- CHAT FUNCTIONS ---

async function createNewChat() {
    const res = await fetch('/api/new_chat');
    const data = await res.json();
    currentSessionId = data.session_id;
    localStorage.setItem('session_id', currentSessionId);
    document.getElementById('chat-box').innerHTML = `
        <div id="welcome-screen" class="flex flex-col items-center justify-center h-full opacity-80 text-center animate-fade-in px-4">
            <img src="/static/images/logo.png" class="w-20 h-20 md:w-24 md:h-24 rounded-full mb-4 md:mb-6 shadow-[0_0_30px_rgba(236,72,153,0.5)] animate-pulse">
            <h2 class="text-2xl md:text-3xl font-bold mb-2">Namaste!</h2>
            <p class="text-sm md:text-base text-gray-400">Main taiyaar hu. Aaj kya create karein?</p>
        </div>
    `;
    loadHistory();
}

async function loadChat(sid) {
    currentSessionId = sid;
    localStorage.setItem('session_id', sid);
    const res = await fetch(`/api/chat/${sid}`);
    const data = await res.json();
    
    const chatBox = document.getElementById('chat-box');
    chatBox.innerHTML = ''; // Clear welcome screen
    
    data.messages.forEach(msg => {
        appendMessage(msg.role === 'user' ? 'user' : 'assistant', msg.content);
    });
}

async function sendMessage() {
    const input = document.getElementById('user-input');
    const msg = input.value.trim();
    if (!msg && !currentFile) return;

    // Clear Welcome Screen if present
    const welcome = document.getElementById('welcome-screen');
    if (welcome) welcome.remove();

    appendMessage('user', msg);
    input.value = '';
    
    // Show Thinking Indicator
    const chatBox = document.getElementById('chat-box');
    const thinkingId = 'thinking_' + Date.now();
    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'msg-ai';
    thinkingDiv.id = thinkingId;
    thinkingDiv.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>';
    chatBox.appendChild(thinkingDiv);
    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const payload = {
            message: msg,
            session_id: currentSessionId,
            mode: currentMode,
            file_data: currentFile ? currentFile.data : null,
            file_type: currentFile ? currentFile.type : null
        };

        const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        
        // Remove thinking indicator
        document.getElementById(thinkingId).remove();
        
        // Clear file after sending
        currentFile = null; 
        
        appendMessage('assistant', data.reply);
        loadHistory(); // Refresh sidebar title

        // Voice Reply (If Enabled)
        if (document.getElementById('voice-toggle') && document.getElementById('voice-toggle').checked) {
            playAudio(data.reply);
        }

    } catch (e) {
        document.getElementById(thinkingId).innerHTML = '<span class="text-red-400">Error: Could not connect to Shanvika.</span>';
    }
}

// --- UPDATED APPEND MESSAGE (With Actions & Time) ---
function appendMessage(role, text) {
    const chatBox = document.getElementById('chat-box');
    const div = document.createElement('div');
    const msgId = 'msg_' + Date.now();
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    div.className = role === 'user' ? 'msg-user' : 'msg-ai';
    
    let content = text;
    if (role === 'assistant') {
        // Parse Markdown
        content = marked.parse(text);
    }

    // --- ACTION BUTTONS HTML ---
    let actionHTML = '';
    if (role === 'assistant') {
        actionHTML = `
            <div class="msg-meta">
                <span class="msg-time">${time}</span>
                <div class="msg-actions">
                    <button class="action-btn" onclick="copyText('${msgId}')" title="Copy"><i class="fas fa-copy"></i></button>
                    <button class="action-btn" onclick="handleFeedback('${msgId}', 'good')" title="Good"><i class="fas fa-thumbs-up"></i></button>
                    <button class="action-btn" onclick="handleFeedback('${msgId}', 'bad')" title="Bad"><i class="fas fa-thumbs-down"></i></button>
                    <button class="action-btn" onclick="shareResponse('${msgId}')" title="Share"><i class="fas fa-share-alt"></i></button>
                </div>
            </div>
        `;
    } else {
        actionHTML = `<div class="msg-meta" style="border-top:none; justify-content:flex-end;"><span class="msg-time">${time}</span></div>`;
    }

    div.innerHTML = `<div id="${msgId}_content">${content}</div> ${actionHTML}`;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;

    // Highlight Code
    if (role === 'assistant') {
        div.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    }
}

// --- FEEDBACK & ACTIONS ---

function copyText(msgId) {
    const content = document.getElementById(msgId + '_content').innerText;
    navigator.clipboard.writeText(content).then(() => {
        const btn = document.querySelector(`button[onclick="copyText('${msgId}')"] i`);
        btn.className = "fas fa-check text-green-400";
        setTimeout(() => btn.className = "fas fa-copy", 2000);
    });
}

function shareResponse(msgId) {
    const content = document.getElementById(msgId + '_content').innerText;
    if (navigator.share) {
        navigator.share({ title: 'Shanvika AI', text: content, url: window.location.href });
    } else {
        copyText(msgId);
        Swal.fire({ icon: 'success', title: 'Copied!', text: 'Link copied to clipboard', timer: 1500, showConfirmButton: false });
    }
}

async function handleFeedback(msgId, type) {
    // Get user email (trick to get from sidebar if logged in)
    const userEmail = document.getElementById('profile-name-sidebar').innerText === 'Guest' ? 'guest' : 'user';

    const options = type === 'good' 
        ? { title: 'Nice! What did you like? 💖', input: 'select', inputOptions: { 'Helpful': 'Helpful', 'Fast': 'Fast', 'Creative': 'Creative' } }
        : { title: 'Oops! What was wrong? 💔', input: 'select', inputOptions: { 'Wrong Info': 'Wrong Info', 'Rude': 'Rude', 'Bug': 'Bug' } };
    
    const { value: category } = await Swal.fire({
        ...options,
        showCancelButton: true,
        confirmButtonColor: type === 'good' ? '#4ade80' : '#f87171',
        confirmButtonText: 'Submit'
    });

    if (category) {
        await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message_id: msgId, user_email: userEmail, type: type, category: category })
        });
        
        // Visual Feedback
        const btn = document.querySelector(`button[onclick="handleFeedback('${msgId}', '${type}')"]`);
        btn.classList.add(type === 'good' ? 'liked' : 'disliked');
        const Toast = Swal.mixin({ toast: true, position: 'top-end', showConfirmButton: false, timer: 2000 });
        Toast.fire({ icon: 'success', title: 'Thanks for feedback!' });
    }
}

// --- FILE UPLOAD ---
function handleFileUpload(input) {
    const file = input.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        currentFile = {
            data: e.target.result.split(',')[1], // Base64
            type: file.type
        };
        // Show preview in chat
        appendMessage('user', `📎 File attached: ${file.name}`);
    };
    reader.readAsDataURL(file);
}

// --- VOICE & MODES ---

function setMode(mode, btn) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    // Quick notification
    const Toast = Swal.mixin({ toast: true, position: 'top', showConfirmButton: false, timer: 1000 });
    Toast.fire({ icon: 'info', title: `Mode switched to ${mode.replace('_', ' ')}` });
}

function toggleRecording() {
    if (!('webkitSpeechRecognition' in window)) {
        alert("Voice not supported in this browser. Use Chrome.");
        return;
    }
    if (isRecording) {
        recognition.stop();
        isRecording = false;
        document.getElementById('mic-btn').classList.remove('text-red-500', 'animate-pulse');
        return;
    }

    recognition = new webkitSpeechRecognition();
    recognition.lang = "en-IN"; // Hinglish support
    recognition.continuous = false;
    recognition.interimResults = false;

    recognition.onstart = () => {
        isRecording = true;
        document.getElementById('mic-btn').classList.add('text-red-500', 'animate-pulse');
    };

    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        document.getElementById('user-input').value = transcript;
        sendMessage(); // Auto send
    };

    recognition.onend = () => {
        isRecording = false;
        document.getElementById('mic-btn').classList.remove('text-red-500', 'animate-pulse');
    };

    recognition.start();
}

async function playAudio(text) {
    try {
        const res = await fetch('/api/speak', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.play();
    } catch (e) { console.error("Audio Error:", e); }
}

// --- SIDEBAR & HISTORY ---

async function loadHistory() {
    const res = await fetch('/api/history');
    const data = await res.json();
    const list = document.getElementById('history-list');
    list.innerHTML = '';
    
    data.history.forEach(chat => {
        const div = document.createElement('div');
        div.className = 'history-item truncate text-xs md:text-sm';
        div.innerHTML = `<i class="far fa-comment-alt mr-2 text-gray-500"></i> ${chat.title}`;
        div.onclick = () => loadChat(chat.id);
        
        // Right click context menu (for rename/delete)
        div.oncontextmenu = (e) => {
            e.preventDefault();
            showContextMenu(e, chat.id);
        };
        list.appendChild(div);
    });
}

// --- PROFILE & SETTINGS ---

async function loadProfile() {
    const res = await fetch('/api/profile');
    const data = await res.json();
    
    // Sidebar Update
    document.getElementById('profile-name-sidebar').innerText = data.name || "User";
    document.getElementById('profile-img-sidebar').src = data.avatar || "/static/images/logo.png";
    document.getElementById('profile-plan-sidebar').innerText = data.plan;

    // Modal Update
    document.getElementById('profile-name-input').value = data.name || "";
    document.getElementById('profile-img-modal').src = data.avatar || "/static/images/logo.png";
}

function openSettingsModal() { document.getElementById('settings-modal').style.display = 'flex'; }
function openProfileModal() { document.getElementById('profile-modal').style.display = 'flex'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }
function toggleVoice() { /* Handled by check in sendMessage */ }

function toggleTheme() {
    document.body.classList.toggle('light-mode');
    localStorage.setItem('theme', document.body.classList.contains('light-mode') ? 'light' : 'dark');
}

async function deleteAllChats() {
    if(confirm("Delete all history? This cannot be undone.")) {
        await fetch('/api/delete_all_chats', { method: 'DELETE' });
        loadHistory();
        createNewChat();
        closeModal('settings-modal');
    }
}