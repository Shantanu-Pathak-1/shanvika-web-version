let currentSessionId = null;
let currentMode = 'chat';
let abortController = null;
let currentFile = null;
let vantaEffect = null;
let isVoiceOn = false;
let recognition = null;
let isRecording = false;
let deferredPrompt; 

document.addEventListener("DOMContentLoaded", () => {
    loadHistory(); loadProfile(); initVanta(); loadMemories();
    setupSpeechRecognition(); 
    registerServiceWorker(); 
});

// SHARED UTILITY (Used by both script.js and tools.js)
function closeModal(id) { document.getElementById(id).style.display = 'none'; }

// ... (PWA & Mic functions same as before) ...
function registerServiceWorker() { if ('serviceWorker' in navigator) navigator.serviceWorker.register('/static/sw.js'); window.addEventListener('beforeinstallprompt', (e) => { e.preventDefault(); deferredPrompt = e; document.getElementById('install-container')?.classList.remove('hidden'); }); }
async function installPWA() { if (deferredPrompt) { deferredPrompt.prompt(); deferredPrompt = null; document.getElementById('install-container').classList.add('hidden'); } }

function setupSpeechRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = false; recognition.lang = 'en-IN'; recognition.interimResults = false;
        recognition.onstart = () => { isRecording = true; const btn = document.getElementById('mic-btn'); btn.classList.add('text-red-500', 'animate-pulse'); btn.innerHTML = '<i class="fas fa-stop-circle"></i>'; };
        recognition.onend = () => { isRecording = false; const btn = document.getElementById('mic-btn'); btn.classList.remove('text-red-500', 'animate-pulse'); btn.innerHTML = '<i class="fas fa-microphone"></i>'; };
        recognition.onresult = (event) => { document.getElementById('user-input').value = event.results[0][0].transcript; document.getElementById('user-input').focus(); };
    } else document.getElementById('mic-btn').style.display = 'none';
}
function toggleRecording() { if (!recognition) return; if (isRecording) recognition.stop(); else recognition.start(); }

// VISUALS
function initVanta() { if (vantaEffect) { vantaEffect.destroy(); vantaEffect = null; } const isLight = document.body.classList.contains('light-mode'); setTimeout(() => { try { if (isLight) vantaEffect = VANTA.RINGS({ el: "#vanta-bg", mouseControls: true, touchControls: true, minHeight: 200, minWidth: 200, scale: 1, backgroundColor: 0xffffff, color: 0xec4899 }); else vantaEffect = VANTA.HALO({ el: "#vanta-bg", mouseControls: true, touchControls: true, minHeight: 200, minWidth: 200, baseColor: 0xca2cac, backgroundColor: 0x000000, amplitudeFactor: 3, xOffset: -0.01, yOffset: 0.06, size: 1.4 }); } catch (e) {} }, 100); }
function toggleTheme() { document.body.classList.toggle('light-mode'); initVanta(); }

// CORE FUNCTIONS
function setMode(m, b) { 
    currentMode = m; 
    document.querySelectorAll('.mode-btn').forEach(x => x.classList.replace('active', 'bg-white/10')); 
    document.querySelectorAll('.mode-btn').forEach(x => x.classList.remove('bg-gradient-to-r', 'from-pink-500', 'to-purple-600', 'border-none')); 
    b.classList.add('active', 'bg-gradient-to-r', 'from-pink-500', 'to-purple-600', 'border-none'); 
    document.getElementById('user-input').placeholder = "Message Shanvika...";
}

function openSettingsModal() { document.getElementById('settings-modal').style.display = 'block'; }
function openProfileModal() { document.getElementById('profile-modal').style.display = 'block'; }
async function saveProfile() { closeModal('profile-modal'); }

async function saveInstructions(btn) { 
    const text = document.getElementById('custom-instruction-box').value; 
    const originalHTML = btn.innerHTML; 
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...'; 
    await fetch('/api/update_instructions', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ instruction: text }) }); 
    btn.innerHTML = '<i class="fas fa-check"></i> Saved!'; 
    setTimeout(() => { btn.innerHTML = originalHTML; }, 2000); 
}

// MESSAGING SYSTEM
async function sendMessage() { 
    const input = document.getElementById('user-input'); 
    const message = input.value.trim(); 
    if (!message && !currentFile) return; 
    
    if (abortController) { abortController.abort(); abortController = null; document.getElementById("loading-bubble")?.remove(); document.querySelector('button[type="submit"] i').className = "fas fa-arrow-up"; document.querySelector('button[type="submit"]').classList.remove("bg-red-500"); appendMessage('shanvika', "🛑 Stopped."); clearFile(); return; } 
    
    if (!currentSessionId) { try { const res = await fetch('/api/new_chat'); const data = await res.json(); currentSessionId = data.session_id; loadHistory(); } catch (e) { return; } } 
    document.getElementById('welcome-screen').style.display = 'none'; 
    
    let displayMsg = message; 
    if (currentFile) displayMsg += ` <br><span class="text-xs text-gray-400 bg-gray-800 px-2 py-1 rounded mt-1 inline-block"><i class="fas fa-file"></i> ${currentFile.name}</span>`; 
    appendMessage('user', displayMsg); 
    input.value = ''; 
    
    abortController = new AbortController(); 
    const btn = document.querySelector('button[type="submit"]'); 
    const icon = btn.querySelector('i'); 
    icon.className = "fas fa-stop"; 
    btn.classList.add("bg-red-500"); 
    
    let loadTxt = "Thinking..."; 
    if (currentMode === 'image_gen') loadTxt = "🎨 Painting..."; else if (currentMode === 'converter') loadTxt = "🔄 Converting..."; 
    
    const chatBox = document.getElementById('chat-box'); 
    const loader = document.createElement('div'); 
    loader.id = "loading-bubble"; 
    loader.className = "p-4 mb-4 rounded-2xl bg-gray-800 w-fit mr-auto border border-gray-700 flex items-center gap-2"; 
    loader.innerHTML = `<i class="fas fa-robot text-pink-500 animate-pulse"></i> <span class="text-gray-400 text-sm">${loadTxt}</span>`; 
    chatBox.appendChild(loader); 
    chatBox.scrollTop = chatBox.scrollHeight; 
    
    try { 
        const payload = { message: message, session_id: currentSessionId, mode: currentMode, file_data: currentFile?.data, file_type: currentFile?.type }; 
        clearFile(); 
        const res = await fetch('/api/chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), signal: abortController.signal }); 
        const data = await res.json(); 
        loader.remove(); 
        if (data.reply) { appendMessage('shanvika', data.reply); speakText(data.reply); } else appendMessage('shanvika', "⚠️ Empty response."); 
    } catch (e) { 
        loader.remove(); 
        if (e.name !== 'AbortError') appendMessage('shanvika', "⚠️ Error."); 
    } finally { 
        abortController = null; 
        icon.className = "fas fa-arrow-up"; 
        btn.classList.remove("bg-red-500"); 
        clearFile(); 
    } 
}

function appendMessage(sender, text) { 
    const box = document.getElementById('chat-box'); 
    const div = document.createElement('div'); 
    div.className = sender === 'user' ? "msg-user" : "msg-ai"; 
    if (text.includes("<img") || text.includes("<div class=\"glass\"")) div.innerHTML = text; 
    else { div.innerHTML = marked.parse(text); div.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b)); } 
    box.appendChild(div); 
    box.scrollTop = box.scrollHeight; 
}

// ... (Baaki standard functions: File, Profile, History, Payment, Memory etc. same as before) ...
// (Assume standard implementations for handleFileUpload, clearFile, loadHistory, etc. are here)
// Just pasting the critical ones to ensure completeness:

async function handleFileUpload(input) { const file = input.files[0]; if (!file) return; const reader = new FileReader(); reader.onload = (e) => { currentFile = { name: file.name, type: file.type, data: e.target.result }; document.getElementById('user-input').focus(); Swal.fire({toast:true, position:'top-end', icon:'success', title:'File Attached', showConfirmButton:false, timer:1500}); }; reader.readAsDataURL(file); }
function clearFile() { currentFile = null; document.getElementById('file-upload').value = ""; }
async function loadHistory() { try { const res = await fetch('/api/history'); const data = await res.json(); const list = document.getElementById('history-list'); list.innerHTML = ''; data.history.forEach(chat => { const div = document.createElement('div'); div.className = "history-item group"; div.innerHTML = `<div class="history-icon shrink-0"><i class="fas fa-comment-alt"></i></div><span class="nav-label flex-1 truncate text-sm px-2">${chat.title}</span><div class="nav-label w-8 flex justify-center"><i class="fas fa-ellipsis-v opacity-0 group-hover:opacity-100 text-gray-500 hover:text-white p-2" onclick="showDropdown(event, '${chat.id}')"></i></div>`; div.onclick = (e) => { if(!e.target.classList.contains('fa-ellipsis-v')) loadChat(chat.id); }; list.appendChild(div); }); } catch (e) {} }
async function loadChat(sid) { currentSessionId = sid; document.getElementById('welcome-screen').style.display = 'none'; document.getElementById('chat-box').innerHTML=''; const res=await fetch(`/api/chat/${sid}`); const d=await res.json(); d.messages.forEach(m => appendMessage(m.role=='user'?'user':'shanvika', m.content)); }
function createNewChat() { currentSessionId = null; document.getElementById('chat-box').innerHTML = document.getElementById('welcome-screen').outerHTML; document.getElementById('welcome-screen').style.display = 'flex'; window.history.pushState({}, '', '/'); }
async function loadProfile() { try { const res = await fetch('/api/profile'); const data = await res.json(); if (data.name) { document.getElementById('profile-name-sidebar').innerText = data.name; document.getElementById('profile-img-sidebar').src = data.avatar || `https://ui-avatars.com/api/?name=${data.name}`; document.getElementById('profile-plan-sidebar').innerHTML = data.plan === "Pro Plan" ? '<i class="fas fa-crown text-[10px] mr-1"></i> Pro Plan' : 'Free Plan'; document.getElementById('profile-plan-sidebar').className = data.plan === "Pro Plan" ? "text-xs text-pink-400 font-bold" : "text-xs text-gray-500"; } } catch (e) {} }
function speakText(text) { if (!isVoiceOn) return; window.speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text.replace(/<[^>]*>/g, '')); window.speechSynthesis.speak(u); }
function toggleVoice() { isVoiceOn = document.getElementById('voice-toggle').checked; if(!isVoiceOn) window.speechSynthesis.cancel(); else speakText("Voice activated."); }
async function loadMemories() { try { const res = await fetch('/api/memories'); const data = await res.json(); const list = document.getElementById('memory-list'); list.innerHTML = ''; data.memories.forEach(mem => { const div = document.createElement('div'); div.className = "flex justify-between items-center bg-white/5 p-2 rounded text-xs text-gray-300"; div.innerHTML = `<span>${mem}</span> <button onclick="deleteMemory('${mem}')" class="text-red-400 hover:text-white"><i class="fas fa-times"></i></button>`; list.appendChild(div); }); } catch (e) {} }
async function addMemory() { const input = document.getElementById('memory-input'); const text = input.value.trim(); if(!text) return; await fetch('/api/add_memory', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ memory_text: text }) }); input.value = ''; loadMemories(); }
async function deleteMemory(text) { if(!confirm("Forget this?")) return; await fetch('/api/delete_memory', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ memory_text: text }) }); loadMemories(); }
async function deleteAllChats() { if(!confirm("Delete ALL History?")) return; await fetch('/api/delete_all_chats', { method: 'DELETE' }); loadHistory(); createNewChat(); }
// ... (Fake Payment Logic same as before) ...
function startPayment() { document.getElementById('payment-modal').style.display = 'flex'; }
async function processFakePayment() { const btn = document.getElementById('pay-btn'); const loader = document.getElementById('pay-loader'); btn.classList.add('hidden'); loader.classList.remove('hidden'); setTimeout(async () => { const res = await fetch('/api/upgrade_plan', { method: 'POST' }); const data = await res.json(); if (data.status === 'success') { loader.innerHTML = '<i class="fas fa-check-circle text-4xl text-green-500"></i><p>Success!</p>'; setTimeout(() => { location.reload(); }, 1500); } }, 2000); }
let activeChatId = null;
function showDropdown(event, sessionId) { event.stopPropagation(); activeChatId = sessionId; const menu = document.getElementById('dropdown'); const rect = event.target.getBoundingClientRect(); menu.style.top = `${rect.bottom + 5}px`; menu.style.left = `${rect.left - 100}px`; menu.classList.add('show'); document.getElementById('act-delete').onclick = () => deleteChat(activeChatId); document.getElementById('act-rename').onclick = () => renameChat(activeChatId); document.addEventListener('click', () => menu.classList.remove('show'), { once: true }); }
async function deleteChat(sid) { if(!confirm("Delete chat?")) return; await fetch(`/api/delete_chat/${sid}`, { method: 'DELETE' }); loadHistory(); if(currentSessionId === sid) createNewChat(); }
async function renameChat(sid) { const newName = prompt("Rename:"); if(newName) { await fetch('/api/rename_chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ session_id: sid, new_title: newName }) }); loadHistory(); } }