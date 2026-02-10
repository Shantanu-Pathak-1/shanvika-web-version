from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random
import uuid
import shutil
import os
import httpx
import asyncio # 👈 Added for async fix
from groq import Groq
from openai import OpenAI
from duckduckgo_search import DDGS

app = FastAPI()

# 1. CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Get Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

def get_groq(): return Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
def get_deepseek(): return OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com") if DEEPSEEK_API_KEY else None

# --- STORAGE ---
CHAT_SESSIONS = {} 
USER_PROFILE = { "name": "Shantanu", "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=Shantanu" }

# --- STATIC SETUP ---
if not os.path.exists("static"): os.makedirs("static")
if not os.path.exists("templates"): os.makedirs("templates")
    
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- MODELS ---
class ChatRequest(BaseModel):
    message: str
    session_id: str
    mode: str
    image: str | None = None

class RenameRequest(BaseModel):
    session_id: str
    new_title: str

class ProfileRequest(BaseModel):
    name: str

# --- HELPER FUNCTIONS ---
def perform_research(query):
    try:
        results = DDGS().text(query, max_results=5)
        if not results: return None
        summary = "📊 **Web Research Results:**\n\n"
        for i, r in enumerate(results, 1):
            summary += f"**{i}. {r['title']}**\n{r['body']}\n🔗 Source: {r['href']}\n\n"
        return summary
    except Exception as e:
        print(f"Research Error: {e}")
        return None

async def generate_image_hf(prompt):
    if not HF_TOKEN: return "⚠️ **Error:** HF_TOKEN missing!"
    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(API_URL, headers=headers, json={"inputs": prompt}, timeout=60.0)
        if response.status_code == 200:
            filename = f"static/gen_{uuid.uuid4().hex[:8]}.png"
            with open(filename, "wb") as f: f.write(response.content)
            return f"🎨 **Image Generated!**<br><img src='/{filename}' class='rounded-lg mt-2 shadow-lg max-w-full' style='max-height: 400px;'>"
        else: return f"⚠️ **Failed:** {response.text[:200]}"
    except Exception as e: return f"⚠️ **Error:** {str(e)}"

# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/profile")
def get_profile(): return USER_PROFILE

@app.post("/api/update_profile_name")
def update_profile_name(req: ProfileRequest):
    USER_PROFILE["name"] = req.name
    return {"status": "success", "name": req.name}

@app.post("/api/update_avatar")
def update_avatar(file: UploadFile = File(...)):
    file_path = f"static/profile_{uuid.uuid4().hex[:8]}.png"
    with open(file_path, "wb+") as buffer: shutil.copyfileobj(file.file, buffer)
    USER_PROFILE["avatar"] = f"/{file_path}"
    return {"status": "success", "avatar": USER_PROFILE["avatar"]}

@app.get("/api/history")
def get_history():
    history = []
    for sid, data in CHAT_SESSIONS.items():
        history.append({"id": sid, "title": data.get("title", "New Chat")})
    return {"history": list(reversed(history))}

@app.get("/api/new_chat")
def create_chat():
    new_id = str(uuid.uuid4())[:8]
    CHAT_SESSIONS[new_id] = {"title": "New Chat", "messages": []}
    return {"session_id": new_id, "messages": []}

@app.get("/api/chat/{session_id}")
def get_chat(session_id: str):
    return {"messages": CHAT_SESSIONS.get(session_id, {}).get("messages", [])}

@app.post("/api/rename_chat")
def rename_chat(req: RenameRequest):
    if req.session_id in CHAT_SESSIONS: CHAT_SESSIONS[req.session_id]["title"] = req.new_title
    return {"status": "success"}

@app.delete("/api/delete_chat/{session_id}")
def delete_chat(session_id: str):
    if session_id in CHAT_SESSIONS: del CHAT_SESSIONS[session_id]
    return {"status": "success"}

# --- MAIN CHAT LOGIC ---
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    sid = req.session_id
    mode = req.mode
    msg = req.message
    img_data = req.image 
    
    if sid not in CHAT_SESSIONS:
        CHAT_SESSIONS[sid] = {"title": "New Chat", "messages": []}
    
    if len(CHAT_SESSIONS[sid]["messages"]) == 0:
        CHAT_SESSIONS[sid]["title"] = " ".join(msg.split()[:5])

    user_content = msg
    if img_data: user_content += " [🖼️ Image Uploaded]"
    CHAT_SESSIONS[sid]["messages"].append({"role": "user", "content": user_content})

    reply = ""
    try:
        # 1. IMAGE GEN
        if mode == "image_gen":
            reply = await generate_image_hf(msg)

        # 2. RESEARCH (Fixed Async Blocking)
        elif mode == "research":
            research_data = await asyncio.to_thread(perform_research, msg)
            client = get_groq()
            if research_data and client:
                completion = client.chat.completions.create(
                    messages=[{"role": "system", "content": f"Summarize:\n{research_data}"}, {"role": "user", "content": msg}],
                    model="llama-3.3-70b-versatile"
                )
                reply = completion.choices[0].message.content
            else:
                reply = research_data if research_data else "⚠️ No results."

        # 3. TEXT & VISION
        else:
            sys_instr = "You are Shanvika AI."
            if mode == "coding": sys_instr += " Expert Coder."
            elif mode == "anime": sys_instr += " Anime expert."
            elif mode == "video": sys_instr += " Video Script Writer."

            if img_data:
                client = get_groq()
                if client:
                    completion = client.chat.completions.create(
                        model="llama-3.2-11b-vision-preview",
                        messages=[{"role": "user", "content": [{"type": "text", "text": f"{sys_instr}\nQuery: {msg}"}, {"type": "image_url", "image_url": {"url": img_data}}]}]
                    )
                    reply = completion.choices[0].message.content
                else: reply = "⚠️ Groq Key missing."
            else:
                client = get_deepseek() if mode == "coding" else get_groq()
                model = "deepseek-chat" if mode == "coding" else "llama-3.3-70b-versatile"
                if client:
                    msgs = [{"role": "system", "content": sys_instr}]
                    msgs.extend(CHAT_SESSIONS[sid]["messages"][-10:])
                    completion = client.chat.completions.create(model=model, messages=msgs)
                    reply = completion.choices[0].message.content
                else: reply = "⚠️ API Key missing."

    except Exception as e:
        reply = f"⚠️ Error: {str(e)}"
        print(f"Error Log: {e}")

    CHAT_SESSIONS[sid]["messages"].append({"role": "assistant", "content": reply})
    return {"reply": reply}