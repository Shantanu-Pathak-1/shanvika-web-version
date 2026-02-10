let currentSessionId = null;
let currentMode = 'chat';
let abortController = null;
let currentFile = null;
let vantaEffect = null;
let isVoiceOn = false;
// New Mic Variables
let recognition = null;
let isRecording = false;

document.addEventListener("DOMContentLoaded", () => {
    loadHistory(); loadProfile(); initVanta(); loadMemories();
    setupSpeechRecognition(); // Init Speech
});

// ==========================================
// 🎙️ MICROPHONE INPUT LOGIC
// ==========================================
function setupSpeechRecognition() {
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        recognition = new SpeechRecognition();
        recognition.continuous = false; // Stop after speaking
        recognition.lang = 'en-IN'; // Indian Accent English/Hindi mix support
        recognition.interimResults = false;

        recognition.onstart = () => {
            isRecording = true;
            const btn = document.getElementById('mic-btn');
            btn.classList.add('text-red-500', 'animate-pulse'); // Red & Pulse effect
            btn.innerHTML = '<i class="fas fa-stop-circle"></i>'; // Change icon to Stop
        };

        recognition.onend = () => {
            isRecording = false;
            const btn = document.getElementById('mic-btn');
            btn.classList.remove('text-red-500', 'animate-pulse');
            btn.innerHTML = '<i class="fas fa-microphone"></i>';
        };

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            const input = document.getElementById('user-input');
            input.value = transcript;
            input.focus(); // Ready to send
        };

        recognition.onerror = (event) => {
            console.error("Mic Error:", event.error);
            isRecording = false;
            alert("Mic Error: " + event.error);
        };
    } else {
        console.log("Browser does not support Speech API");
        document.getElementById('mic-btn').style.display = 'none';
    }
}

function toggleRecording() {
    if (!recognition) return;
    if (isRecording) {
        recognition.stop();
    } else {
        recognition.start();
    }
}

// ... (Baaki poora code same hai, bas copy-paste karo) ...
// Vanta & Theme
function initVanta() { if (vantaEffect) { vantaEffect.destroy(); vantaEffect = null; } const isLight = document.body.classList.contains('light-mode'); setTimeout(() => { try { if (isLight) vantaEffect = VANTA.RINGS({ el: "#vanta-bg", mouseControls: true, touchControls: true, minHeight: 200, minWidth: 200, scale: 1, backgroundColor: 0xffffff, color: 0xec4899 }); else vantaEffect = VANTA.HALO({ el: "#vanta-bg", mouseControls: true, touchControls: true, minHeight: 200, minWidth: 200, baseColor: 0xca2cac, backgroundColor: 0x000000, amplitudeFactor: 3, xOffset: -0.01, yOffset: 0.06, size: 1.4 }); } catch (e) {} }, 100); }
function toggleTheme() { document.body.classList.toggle('light-mode'); initVanta(); }

// Profile
async function loadProfile() { try { const res = await fetch('/api/profile'); const data = await res.json(); if (data.name) { document.getElementById('profile-name-sidebar').innerText = data.name; const imgSrc = data.avatar || `https://ui-avatars.com/api/?name=${data.name}&background=random&color=fff`; document.getElementById('profile-img-sidebar').src = imgSrc; document.getElementById('profile-img-modal').src = imgSrc; document.getElementById('profile-name-input').value = data.name; document.getElementById('custom-instruction-box').value = data.custom_instruction; } } catch (e) {} }

// File Upload
async function handleFileUpload(input) { const file = input.files[0]; if (!file) return; if (file.size > 15 * 1024 * 1024) { alert("File > 15MB!"); input.value = ""; return; } const sendBtn = document.querySelector('button[type="submit"]'); sendBtn.disabled = true; sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin text-pink-500"></i>'; const wrapper = document.querySelector('.input-wrapper'); const oldP = document.getElementById('file-preview'); if(oldP) oldP.remove(); const div = document.createElement('div'); div.id = "file-preview"; div.className = "flex items-center gap-2 bg-gray-800 text-white px-3 py-2 rounded-lg mb-2 w-fit text-sm border border-gray-600 animate-pulse"; div.innerHTML = `<i class="fas fa-file"></i> <span>${file.name}</span>`; wrapper.insertBefore(div, wrapper.querySelector('.input-container')); try { const base64 = await toBase64(file); currentFile = { name: file.name, type: file.type, data: base64 }; div.innerHTML = `<i class="fas fa-file"></i> <span>${file.name}</span> <span class="text-xs text-green-400 ml-2">Ready</span> <button onclick="clearFile()" class="ml-2 text-gray-400"><i class="fas fa-times"></i></button>`; div.classList.remove('animate-pulse'); } catch (e) { clearFile(); } finally { sendBtn.disabled = false; sendBtn.innerHTML = '<i class="fas fa-arrow-up"></i>'; } }
function clearFile() { currentFile = null; document.getElementById('file-upload').value = ""; const p = document.getElementById('file-preview'); if(p) p.remove(); }
const toBase64 = file => new Promise((r, j) => { const rd = new FileReader(); rd.readAsDataURL(file); rd.onload = () => r(rd.result); rd.onerror = j; });

// Memories
async function loadMemories() { try { const res = await fetch('/api/memories'); const data = await res.json(); const list = document.getElementById('memory-list'); list.innerHTML = ''; data.memories.forEach(mem => { const div = document.createElement('div'); div.className = "flex justify-between items-center bg-white/5 p-2 rounded text-xs text-gray-300"; div.innerHTML = `<span>${mem}</span> <button onclick="deleteMemory('${mem}')" class="text-red-400 hover:text-white"><i class="fas fa-times"></i></button>`; list.appendChild(div); }); } catch (e) {} }
async function addMemory() { const input = document.getElementById('memory-input'); const text = input.value.trim(); if(!text) return; await fetch('/api/add_memory', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ memory_text: text }) }); input.value = ''; loadMemories(); }
async function deleteMemory(text) { if(!confirm("Forget this?")) return; await fetch('/api/delete_memory', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ memory_text: text }) }); loadMemories(); }
async function deleteAllChats() { if(!confirm("⚠️ Delete ALL History?")) return; await fetch('/api/delete_all_chats', { method: 'DELETE' }); loadHistory(); createNewChat(); alert("History Cleared."); }

// Voice Output
function toggleVoice() { isVoiceOn = document.getElementById('voice-toggle').checked; if(!isVoiceOn) window.speechSynthesis.cancel(); else speakText("Voice activated."); }
function speakText(text) { if (!isVoiceOn) return; window.speechSynthesis.cancel(); const cleanText = text.replace(/[*#_`]/g, '').replace(/<[^>]*>/g, ''); const utterance = new SpeechSynthesisUtterance(cleanText); const voices = window.speechSynthesis.getVoices(); const preferred = voices.find(v => v.lang.includes('hi') || v.name.includes('Google हिन्दी') || v.name.includes('Female')); if (preferred) utterance.voice = preferred; utterance.pitch = 1.1; window.speechSynthesis.speak(utterance); }
window.speechSynthesis.onvoiceschanged = () => {};

// Chat Logic
async function sendMessage() {
    const input = document.getElementById('user-input');
    const message = input.value.trim();
    if (!message && !currentFile) return;
    if (abortController) { abortController.abort(); abortController = null; document.getElementById("loading-bubble")?.remove(); document.querySelector('button[type="submit"] i').className = "fas fa-arrow-up"; document.querySelector('button[type="submit"]').classList.remove("bg-red-500"); appendMessage('shanvika', "🛑 Stopped."); clearFile(); return; }
    if (!currentSessionId) { try { const res = await fetch('/api/new_chat'); const data = await res.json(); currentSessionId = data.session_id; loadHistory(); } catch (e) { return; } }
    document.getElementById('welcome-screen').style.display = 'none';
    let displayMsg = message; if (currentFile) displayMsg += ` <br><span class="text-xs text-gray-400 bg-gray-800 px-2 py-1 rounded mt-1 inline-block"><i class="fas fa-file"></i> ${currentFile.name}</span>`;
    appendMessage('user', displayMsg); input.value = '';
    abortController = new AbortController(); const btn = document.querySelector('button[type="submit"]'); const icon = btn.querySelector('i'); icon.className = "fas fa-stop"; btn.classList.add("bg-red-500");
    let loadTxt = "Thinking..."; if (currentMode === 'image_gen') loadTxt = "🎨 Painting..."; else if (currentMode === 'converter') loadTxt = "🔄 Converting...";
    const chatBox = document.getElementById('chat-box'); const loader = document.createElement('div'); loader.id = "loading-bubble"; loader.className = "p-4 mb-4 rounded-2xl bg-gray-800 w-fit mr-auto border border-gray-700 flex items-center gap-2"; loader.innerHTML = `<i class="fas fa-robot text-pink-500 animate-pulse"></i> <span class="text-gray-400 text-sm">${loadTxt}</span>`; chatBox.appendChild(loader); chatBox.scrollTop = chatBox.scrollHeight;
    try { const payload = { message: message, session_id: currentSessionId, mode: currentMode, file_data: currentFile?.data, file_type: currentFile?.type }; clearFile(); const res = await fetch('/api/chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload), signal: abortController.signal }); const data = await res.json(); loader.remove(); if (data.reply) { appendMessage('shanvika', data.reply); speakText(data.reply); } else appendMessage('shanvika', "⚠️ Empty response."); } catch (e) { loader.remove(); if (e.name !== 'AbortError') appendMessage('shanvika', "⚠️ Error."); } finally { abortController = null; icon.className = "fas fa-arrow-up"; btn.classList.remove("bg-red-500"); clearFile(); }
}
function appendMessage(sender, text) { const box = document.getElementById('chat-box'); const div = document.createElement('div'); div.className = sender === 'user' ? "msg-user" : "msg-ai"; if (text.includes("<img") || text.includes("<video") || text.includes("<a href")) div.innerHTML = text; else { div.innerHTML = marked.parse(text); div.querySelectorAll('pre code').forEach(b => hljs.highlightElement(b)); } box.appendChild(div); box.scrollTop = box.scrollHeight; }

// History
async function loadHistory() { try { const res = await fetch('/api/history'); const data = await res.json(); const list = document.getElementById('history-list'); list.innerHTML = ''; data.history.forEach(chat => { const div = document.createElement('div'); div.className = "history-item group"; div.innerHTML = `<div class="history-icon shrink-0"><i class="fas fa-comment-alt"></i></div><span class="nav-label flex-1 truncate text-sm px-2">${chat.title}</span><div class="nav-label w-8 flex justify-center"><i class="fas fa-ellipsis-v opacity-0 group-hover:opacity-100 text-gray-500 hover:text-white p-2" onclick="showDropdown(event, '${chat.id}')"></i></div>`; div.onclick = (e) => { if(!e.target.classList.contains('fa-ellipsis-v')) loadChat(chat.id); }; list.appendChild(div); }); } catch (e) {} }
let activeChatId = null;
function showDropdown(event, sessionId) { event.stopPropagation(); activeChatId = sessionId; const menu = document.getElementById('dropdown'); const rect = event.target.getBoundingClientRect(); menu.style.top = `${rect.bottom + 5}px`; menu.style.left = `${rect.left - 100}px`; menu.classList.add('show'); document.getElementById('act-delete').onclick = () => deleteChat(activeChatId); document.getElementById('act-rename').onclick = () => renameChat(activeChatId); document.addEventListener('click', () => menu.classList.remove('show'), { once: true }); }
async function deleteChat(sid) { if(!confirm("Delete this chat?")) return; await fetch(`/api/delete_chat/${sid}`, { method: 'DELETE' }); loadHistory(); if(currentSessionId === sid) createNewChat(); }
async function renameChat(sid) { const newName = prompt("Rename Chat:"); if(newName) { await fetch('/api/rename_chat', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ session_id: sid, new_title: newName }) }); loadHistory(); } }
async function loadChat(sid) { currentSessionId = sid; document.getElementById('welcome-screen').style.display = 'none'; document.getElementById('chat-box').innerHTML=''; const res=await fetch(`/api/chat/${sid}`); const d=await res.json(); d.messages.forEach(m => appendMessage(m.role=='user'?'user':'shanvika', m.content)); }
function createNewChat() { currentSessionId = null; document.getElementById('chat-box').innerHTML = document.getElementById('welcome-screen').outerHTML; document.getElementById('welcome-screen').style.display = 'flex'; window.history.pushState({}, '', '/'); }
function setMode(m, b) { currentMode = m; document.querySelectorAll('.mode-btn').forEach(x => x.classList.replace('active', 'bg-white/10')); document.querySelectorAll('.mode-btn').forEach(x => x.classList.remove('bg-gradient-to-r', 'from-pink-500', 'to-purple-600', 'border-none')); b.classList.add('active', 'bg-gradient-to-r', 'from-pink-500', 'to-purple-600', 'border-none'); }
function openSettingsModal() { document.getElementById('settings-modal').style.display = 'block'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }
function openProfileModal() { document.getElementById('profile-modal').style.display = 'block'; }
async function saveProfile() { closeModal('profile-modal'); }
async function saveInstructions(btn) { const text = document.getElementById('custom-instruction-box').value; const originalHTML = btn.innerHTML; const originalClasses = btn.className; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...'; await fetch('/api/update_instructions', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ instruction: text }) }); btn.className = "mt-2 w-full bg-green-600 text-white border border-green-600 py-2 rounded font-bold transition text-sm flex items-center justify-center gap-2"; btn.innerHTML = '<i class="fas fa-check"></i> Saved!'; setTimeout(() => { btn.className = originalClasses; btn.innerHTML = originalHTML; }, 2000); }