// --- CONFIG ---
let currentMode = 'chat';
let currentSessionId = null;
let vantaEffect = null;
let isDarkMode = true;
let selectedImageBase64 = null; // 👈 Store Image Data

document.addEventListener('DOMContentLoaded', () => {
    loadProfile();
    loadHistory(); 
    initVanta();
});

// --- VANTA ---
function initVanta() {
    if (!vantaEffect && isDarkMode) {
        try {
            vantaEffect = VANTA.HALO({
                el: "#vanta-bg", mouseControls: true, touchControls: true, minHeight: 200, minWidth: 200,
                backgroundColor: 0x171718, baseColor: 0x1a59, amplitudeFactor: 3
            });
        } catch(e) { console.log("Vanta init failed:", e); }
    }
}

// --- THEME ---
function toggleTheme() {
    isDarkMode = !isDarkMode;
    document.body.className = isDarkMode ? "flex h-screen w-full dark-mode" : "flex h-screen w-full light-mode";
    document.getElementById('theme-btn').innerText = isDarkMode ? "Dark" : "Light";
    
    const footer = document.querySelector('.input-fixed-bottom');
    if (!isDarkMode) {
        footer.style.background = 'white'; 
        footer.style.borderTop = '1px solid #e5e7eb';
    } else {
        footer.style.background = 'linear-gradient(to top, #000000, rgba(0,0,0,0.9), transparent)';
        footer.style.borderTop = 'none';
    }
    if(isDarkMode) initVanta(); else { if(vantaEffect) { vantaEffect.destroy(); vantaEffect = null; } }
}

// --- PROFILE ---
async function loadProfile() {
    try {
        const res = await fetch('/api/profile');
        const data = await res.json();
        const avatarUrl = data.avatar + "?t=" + new Date().getTime();
        document.getElementById('profile-img-sidebar').src = avatarUrl;
        document.getElementById('profile-img-modal').src = avatarUrl;
        document.getElementById('profile-name-sidebar').innerText = data.name;
        document.getElementById('profile-name-input').value = data.name;
    } catch(e){ console.error("Profile load error:", e); }
}

async function saveProfile() {
    const name = document.getElementById('profile-name-input').value;
    try {
        await fetch('/api/update_profile_name', { 
            method: 'POST', 
            headers: {'Content-Type': 'application/json'}, 
            body: JSON.stringify({name}) 
        });
        loadProfile(); closeModal('profile-modal');
    } catch(e) { console.error("Save profile error:", e); }
}

async function uploadAvatar(input) {
    if(!input.files[0]) return;
    const fd = new FormData(); fd.append("file", input.files[0]);
    try { await fetch('/api/update_avatar', { method: 'POST', body: fd }); loadProfile(); } catch(e) { console.error("Avatar upload error:", e); }
}

// --- CHAT & IMAGE ---
function setMode(mode, btn) {
    currentMode = mode;
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const placeholders = {
        'chat': 'Message Shanvika...', 'coding': 'Ask for code help...',
        'image_gen': 'Describe image to generate...', 'research': 'What do you want to research?...',
        'anime': 'Ask about anime...', 'video': 'Describe your video idea...'
    };
    document.getElementById('user-input').placeholder = placeholders[mode] || 'Message Shanvika...';
}

// 🖼️ HANDLE FILE SELECTION
function handleFileUpload(input) { 
    const file = input.files[0];
    if(!file) return;

    // Convert to Base64
    const reader = new FileReader();
    reader.onload = function(e) {
        selectedImageBase64 = e.target.result;
        // UI feedback
        const btn = document.querySelector('.fa-paperclip').parentElement;
        btn.style.color = '#4ade80'; // Green color
        document.getElementById('user-input').placeholder = "Image selected! Type question & send...";
        document.getElementById('user-input').focus();
    };
    reader.readAsDataURL(file);
}

async function createNewChat() {
    try {
        const res = await fetch('/api/new_chat');
        const data = await res.json();
        currentSessionId = data.session_id;
        
        document.getElementById('chat-box').innerHTML = `
            <div id="welcome-screen" class="flex flex-col items-center justify-center h-full opacity-60 text-center">
                <div class="w-20 h-20 rounded-full bg-gradient-to-tr from-pink-500 to-purple-600 flex items-center justify-center text-4xl mb-4 shadow-2xl">🌸</div>
                <h2 class="text-2xl font-bold">Namaste!</h2>
                <p>Select a mode below to start.</p>
            </div>`;
        await loadHistory();
    } catch(e) { console.error("Create chat error:", e); }
}

async function sendMessage() {
    const input = document.getElementById('user-input');
    const msg = input.value.trim();
    
    if(!msg && !selectedImageBase64) return; // Msg or Image required
    
    if(!currentSessionId) {
        await createNewChat();
        await new Promise(r => setTimeout(r, 200)); 
    }

    // Show User Message with Image Preview if exists
    let userDisplayHtml = msg;
    if(selectedImageBase64) {
        userDisplayHtml += `<br><img src="${selectedImageBase64}" class="mt-2 rounded-lg max-h-40 border border-white/20">`;
    }
    appendMessage(userDisplayHtml, 'user');
    
    input.value = '';
    
    // Reset Upload Button
    const btn = document.querySelector('.fa-paperclip').parentElement;
    btn.style.color = ''; 

    try {
        const res = await fetch('/api/chat', {
            method: 'POST', 
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                message: msg || "Analyze this image", // Fallback text if empty
                session_id: currentSessionId, 
                mode: currentMode,
                image: selectedImageBase64 // 👈 Sending Image
            })
        });
        
        // Clear selected image after sending
        selectedImageBase64 = null;
        document.getElementById('file-upload').value = ""; // Clear input

        if (!res.ok) throw new Error(`Server error: ${res.status}`);
        const data = await res.json();
        appendMessage(data.reply, 'ai');
        loadHistory(); 
        
    } catch(e) { 
        console.error("Send message error:", e);
        appendMessage("⚠️ Error: Could not connect to Shanvika.", 'ai'); 
    }
}

function appendMessage(htmlContent, role) {
    const welcome = document.getElementById('welcome-screen');
    if(welcome) welcome.style.display = 'none';

    const box = document.getElementById('chat-box');
    const div = document.createElement('div');
    div.className = `flex gap-4 mb-4 ${role === 'user' ? 'flex-row-reverse' : ''}`;
    const avatar = role === 'ai' ? 
        '<div class="w-8 h-8 rounded-full bg-pink-600 flex items-center justify-center text-xs text-white">🌸</div>' : 
        '<div class="w-8 h-8 rounded-full bg-gray-600 flex items-center justify-center text-xs text-white">U</div>';
    
    div.innerHTML = `${avatar}<div class="${role === 'ai' ? 'msg-ai' : 'msg-user'} p-3 px-4 max-w-[85%] text-sm leading-relaxed shadow-md">${htmlContent}</div>`;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

// --- HISTORY ---
async function loadHistory() {
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        const list = document.getElementById('history-list');
        list.innerHTML = "";
        data.history.forEach(chat => {
            const div = document.createElement('div');
            div.className = "p-3 rounded-lg flex items-center justify-between cursor-pointer hover:bg-white/5 mb-1 group transition";
            div.onclick = (e) => { if(!e.target.closest('button')) loadChat(chat.id); };
            div.innerHTML = `<div class="flex items-center gap-3 overflow-hidden"><i class="far fa-comment-alt text-gray-500"></i><span class="nav-label text-gray-400 text-sm truncate w-32 group-hover:text-white transition">${chat.title}</span></div><button class="text-gray-500 hover:text-white opacity-0 group-hover:opacity-100 transition" onclick="showMenu(event, '${chat.id}')"><i class="fas fa-ellipsis-h"></i></button>`;
            list.appendChild(div);
        });
    } catch(e){ console.error(e); }
}

async function loadChat(sid) {
    try {
        currentSessionId = sid;
        const res = await fetch(`/api/chat/${sid}`);
        const data = await res.json();
        document.getElementById('chat-box').innerHTML = '';
        data.messages.forEach(m => { appendMessage(m.content, m.role === 'user' ? 'user' : 'ai'); });
    } catch(e) { console.error(e); }
}

// Modals & Menu
function openSettingsModal() { document.getElementById('settings-modal').style.display = 'block'; }
function openProfileModal() { document.getElementById('profile-modal').style.display = 'block'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }

const dd = document.getElementById('dropdown');
function showMenu(e, sid) {
    e.stopPropagation();
    const rect = e.currentTarget.getBoundingClientRect();
    dd.style.top = rect.bottom + 'px'; dd.style.left = rect.left + 'px'; dd.style.display = 'block';
    document.getElementById('act-rename').onclick = async () => { const t = prompt("Rename:"); if(t) { await fetch('/api/rename_chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({session_id: sid, new_title: t}) }); loadHistory(); } dd.style.display = 'none'; };
    document.getElementById('act-delete').onclick = async () => { if(confirm("Delete?")) { await fetch(`/api/delete_chat/${sid}`, {method:'DELETE'}); if(currentSessionId === sid) { currentSessionId = null; createNewChat(); } loadHistory(); } dd.style.display = 'none'; };
}
window.onclick = (e) => { if(!dd.contains(e.target) && !e.target.closest('.fa-ellipsis-h')) { dd.style.display = 'none'; } }

// --- CUSTOM INSTRUCTIONS LOGIC ---

// 1. Load Instruction when Profile Loads
async function loadProfile() {
    try {
        const res = await fetch("/api/profile");
        const data = await res.json();
        if (data.email) {
            document.getElementById("profile-name-sidebar").innerText = data.name;
            document.getElementById("profile-img-sidebar").src = data.avatar;
            document.getElementById("profile-img-modal").src = data.avatar;
            document.getElementById("profile-name-input").value = data.name;
            
            // 👇 Load Saved Instruction into Box
            if(data.custom_instruction) {
                document.getElementById("custom-instruction-box").value = data.custom_instruction;
                document.getElementById("char-count").innerText = data.custom_instruction.length + "/1000";
            }
        }
    } catch (e) { console.error(e); }
}

// 2. Save Instruction Function
async function saveInstructions() {
    const text = document.getElementById("custom-instruction-box").value;
    
    const btn = event.target;
    const originalText = btn.innerHTML;
    btn.innerHTML = "<i class='fas fa-spinner fa-spin'></i> Saving...";
    
    try {
        await fetch("/api/update_instructions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ instruction: text })
        });
        
        // Show Success Feedback
        btn.innerHTML = "<i class='fas fa-check'></i> Saved!";
        setTimeout(() => btn.innerHTML = originalText, 2000);
        
    } catch (e) {
        alert("Error saving instructions");
        btn.innerHTML = originalText;
    }
}

// 3. Character Counter
document.getElementById("custom-instruction-box").addEventListener("input", function() {
    document.getElementById("char-count").innerText = this.value.length + "/1000";
});

// Call loadProfile on startup
loadProfile();