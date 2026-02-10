from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import uuid
import os
import httpx # Async requests
import base64 # Image handling
from groq import Groq
from duckduckgo_search import DDGS
import google.generativeai as genai
import io
import PyPDF2
from docx import Document
import PIL.Image # For Gemini Vision

# ==========================================
# 🔑 KEYS & CONFIG (Render Env Vars se load honge)
# ==========================================
# Ye sab keys Render ke "Environment Variables" section mein add karni hongi
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_random_string_shanvika")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# AI Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN") # Hugging Face Token (Image/Video/Anime ke liye)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY") # Research ke liye (Optional, but recommended)
MONGO_URL = os.getenv("MONGO_URL")

# Gemini Setup
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI()

# 👇 HTTPS LOOP FIX (Render ke liye zaroori hai)
@app.middleware("http")
async def fix_google_oauth_redirect(request: Request, call_next):
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"
    response = await call_next(request)
    return response

# Session Middleware
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=True, same_site="lax")

# Google OAuth
oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# MongoDB Connection
client = AsyncIOMotorClient(MONGO_URL)
db = client.shanvika_db
users_collection = db.users
chats_collection = db.chats

# Static & Templates
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- 🧠 HELPER FUNCTIONS (The Brain of Shanvika) ---

def get_groq(): return Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
async def get_current_user(request: Request): return request.session.get('user')

# 1. GENERATE IMAGE (Hugging Face with Fallback)
async def generate_image_hf(prompt):
    if not HF_TOKEN: return "⚠️ **Error:** HF_TOKEN missing in Render Environment Variables!"
    
    # Priority: SDXL (Best) -> SD 1.5 (Backup)
    models = [
        "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0",
        "https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5"
    ]
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    
    async with httpx.AsyncClient() as client:
        for model_url in models:
            try:
                # 'wait_for_model': True means agar model so raha hai to jagayega
                response = await client.post(model_url, headers=headers, json={"inputs": prompt, "options": {"use_cache": False, "wait_for_model": True}}, timeout=45.0)
                if response.status_code == 200:
                    img_b64 = base64.b64encode(response.content).decode("utf-8")
                    return f"""🎨 **Image Generated:**<br><img src='data:image/png;base64,{img_b64}' class='rounded-lg mt-2 shadow-lg w-full hover:scale-105 transition-transform duration-300'>"""
            except Exception as e:
                print(f"Model failed: {e}")
                continue
    return "⚠️ **Image Gen Failed:** Server busy hai, please retry."

# 2. GENERATE VIDEO (Text-to-Video)
async def generate_video_hf(prompt):
    if not HF_TOKEN: return "⚠️ HF_TOKEN missing!"
    API_URL = "https://api-inference.huggingface.co/models/damo-vilab/text-to-video-ms-1.7b"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(API_URL, headers=headers, json={"inputs": prompt}, timeout=90.0) # Video takes time
            if response.status_code == 200:
                vid_b64 = base64.b64encode(response.content).decode("utf-8")
                return f"""🎥 **Video Generated:**<br><video controls autoplay loop class='rounded-lg mt-2 shadow-lg w-full'><source src='data:video/mp4;base64,{vid_b64}' type='video/mp4'></video>"""
            return f"⚠️ **Video Failed:** Status {response.status_code} (Try simpler prompt)"
    except Exception as e: return f"⚠️ **Error:** {str(e)}"

# 3. ANIME CONVERTER (Image-to-Image)
async def convert_to_anime(file_data):
    if not HF_TOKEN: return "⚠️ HF_TOKEN missing!"
    # Model: Arcane Diffusion (Good for style transfer)
    API_URL = "https://api-inference.huggingface.co/models/nitrosocke/Arcane-Diffusion"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}

    try:
        # Convert base64 back to raw bytes
        if "," in file_data: header, encoded = file_data.split(",", 1)
        else: encoded = file_data
        image_bytes = base64.b64decode(encoded)

        async with httpx.AsyncClient() as client:
            # Post raw bytes for img2img
            response = await client.post(API_URL, headers=headers, content=image_bytes, timeout=50.0)
            if response.status_code == 200:
                img_b64 = base64.b64encode(response.content).decode("utf-8")
                return f"""✨ **Anime Version:**<br><img src='data:image/png;base64,{img_b64}' class='rounded-lg mt-2 w-full'>"""
            return f"⚠️ **Conversion Failed:** Status {response.status_code}"
    except Exception as e: return f"⚠️ **Error:** {str(e)}"

# 4. RESEARCH MODE (Tavily AI -> DDG Fallback)
async def perform_research_task(query):
    # Method A: Tavily API (Best for AI)
    if TAVILY_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                payload = {"api_key": TAVILY_API_KEY, "query": query, "search_depth": "basic", "max_results": 3}
                resp = await client.post("https://api.tavily.com/search", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    summary = "📊 **Latest Research (Source: Tavily):**\n\n"
                    for res in data.get("results", []):
                        summary += f"🔹 **{res['title']}**\n{res['content']}\n🔗 [Read More]({res['url']})\n\n"
                    return summary
        except Exception as e: print(f"Tavily failed: {e}")

    # Method B: DuckDuckGo (Fallback)
    try:
        results = DDGS().text(query, max_results=4)
        if not results: return "⚠️ No results found."
        summary = "📊 **Web Research (Source: DuckDuckGo):**\n\n"
        for r in results:
            summary += f"🔹 **{r['title']}**\n{r['body']}\n🔗 {r['href']}\n\n"
        return summary
    except Exception as e: return f"⚠️ Research Error: {e}"

# 5. GEMINI TEXT
async def generate_gemini(prompt, system_instr):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash') 
        full_prompt = f"System Instruction: {system_instr}\n\nUser Query: {prompt}"
        response = model.generate_content(full_prompt)
        return response.text
    except:
        model = genai.GenerativeModel('gemini-1.5-flash') # Fallback
        return model.generate_content(prompt).text

# --- DATA MODELS ---
class ChatRequest(BaseModel):
    message: str
    session_id: str
    mode: str = "chat" # chat, coding, image_gen, video, research, anime
    file_data: str | None = None
    file_type: str | None = None

class RenameRequest(BaseModel):
    session_id: str
    new_title: str

class ProfileRequest(BaseModel):
    name: str

class InstructionRequest(BaseModel):
    instruction: str

# --- ROUTES ---

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request): return templates.TemplateResponse("login.html", {"request": request})

@app.get("/auth/login")
async def login(request: Request):
    redirect_uri = str(request.url_for('auth_callback'))
    if "onrender.com" in redirect_uri: redirect_uri = redirect_uri.replace("http://", "https://")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if user_info:
            request.session['user'] = dict(user_info)
            email = user_info.get('email')
            if not await users_collection.find_one({"email": email}):
                await users_collection.insert_one({"email": email, "name": user_info.get('name'), "picture": user_info.get('picture'), "role": "user", "custom_instruction": ""})
        return RedirectResponse(url="/")
    except: return RedirectResponse(url="/login")

@app.get("/logout")
async def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse(url="/login")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse(url="/login")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

# Profile & Chat Management APIs
@app.get("/api/profile")
async def get_profile(request: Request):
    user = await get_current_user(request)
    if not user: return {}
    db_user = await users_collection.find_one({"email": user['email']})
    return {"name": db_user.get("name"), "avatar": db_user.get("picture"), "custom_instruction": db_user.get("custom_instruction", "")}

@app.post("/api/update_profile_name")
async def update_name(req: ProfileRequest, request: Request):
    user = await get_current_user(request)
    if user: await users_collection.update_one({"email": user['email']}, {"$set": {"name": req.name}})
    return {"status": "ok"}

@app.post("/api/update_instructions")
async def update_instr(req: InstructionRequest, request: Request):
    user = await get_current_user(request)
    if user: await users_collection.update_one({"email": user['email']}, {"$set": {"custom_instruction": req.instruction}})
    return {"status": "ok"}

@app.get("/api/history")
async def get_history(request: Request):
    user = await get_current_user(request)
    if not user: return {"history": []}
    chats = await chats_collection.find({"user_email": user['email']}).to_list(length=100)
    return {"history": [{"id": c["session_id"], "title": c.get("title", "Chat")} for c in reversed(chats)]}

@app.get("/api/new_chat")
async def create_chat(request: Request):
    user = await get_current_user(request)
    if not user: return {"error": "Login required"}
    sid = str(uuid.uuid4())[:8]
    await chats_collection.insert_one({"session_id": sid, "user_email": user['email'], "title": "New Chat", "messages": []})
    return {"session_id": sid, "messages": []}

@app.get("/api/chat/{session_id}")
async def get_chat(session_id: str, request: Request):
    user = await get_current_user(request)
    chat = await chats_collection.find_one({"session_id": session_id, "user_email": user['email']})
    return {"messages": chat.get("messages", []) if chat else []}

@app.post("/api/rename_chat")
async def rename_chat(req: RenameRequest, request: Request):
    user = await get_current_user(request)
    await chats_collection.update_one({"session_id": req.session_id, "user_email": user['email']}, {"$set": {"title": req.new_title}})
    return {"status": "ok"}

@app.delete("/api/delete_chat/{session_id}")
async def delete_chat(session_id: str, request: Request):
    user = await get_current_user(request)
    await chats_collection.delete_one({"session_id": session_id, "user_email": user['email']})
    return {"status": "ok"}

# ==========================================
# 🤖 MAIN CHAT CONTROLLER
# ==========================================
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    user = await get_current_user(request)
    if not user: return {"reply": "⚠️ Please Login first."}

    sid, mode, msg = req.session_id, req.mode, req.message
    
    # 1. FILE PARSING (PDF/DOCX/IMAGE)
    file_text = ""
    vision_object = None # For Gemini
    vision_url = None # For Groq
    
    if req.file_data:
        try:
            if "," in req.file_data: header, encoded = req.file_data.split(",", 1)
            else: encoded = req.file_data
            decoded = base64.b64decode(encoded)
            
            if "pdf" in (req.file_type or ""):
                reader = PyPDF2.PdfReader(io.BytesIO(decoded))
                file_text = "\n[PDF CONTENT]:\n" + "\n".join([p.extract_text() for p in reader.pages])
            elif "image" in (req.file_type or ""):
                vision_url = req.file_data
                vision_object = PIL.Image.open(io.BytesIO(decoded))
                msg += " [Image Attached]"
        except Exception as e:
            return {"reply": f"⚠️ File Error: {e}"}

    # 2. SYSTEM INSTRUCTION
    db_user = await users_collection.find_one({"email": user['email']})
    custom_instr = db_user.get("custom_instruction", "")
    base_system = "You are Shanvika AI, a helpful assistant."
    if custom_instr: base_system += f"\nUser Preferences: {custom_instr}"
    if mode == "coding": base_system += " You are an Expert Coder. Provide clean code."
    
    # Update Chat History
    chat_exists = await chats_collection.find_one({"session_id": sid})
    if not chat_exists:
        await chats_collection.insert_one({"session_id": sid, "user_email": user['email'], "title": msg[:30], "messages": []})
    
    await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "user", "content": msg + file_text}}})

    # 3. ROUTING LOGIC (The Magic ✨)
    reply = ""
    
    # A. IMAGE GENERATION
    if mode == "image_gen":
        reply = await generate_image_hf(msg)
        
    # B. VIDEO GENERATION
    elif mode == "video":
        reply = await generate_video_hf(msg)
        
    # C. ANIME CONVERSION (Image Upload Required)
    elif mode == "anime":
        if req.file_data:
            reply = await convert_to_anime(req.file_data)
        else:
            # Agar image nahi hai, toh Text-to-Image use karo with "Anime Style" prompt
            reply = await generate_image_hf(msg + ", anime style, studio ghibli style, vibrant colors")
            
    # D. RESEARCH MODE
    elif mode == "research":
        research_data = await perform_research_task(msg)
        # Combine Research with LLM for final answer
        client = get_groq()
        if client:
            completion = client.chat.completions.create(
                messages=[{"role": "system", "content": base_system}, {"role": "user", "content": f"Information: {research_data}\n\nUser Question: {msg}\n\nSummarize the information to answer the question."}],
                model="llama-3.3-70b-versatile"
            )
            reply = completion.choices[0].message.content
        else:
            reply = research_data # Agar Groq fail ho jaye toh raw data dikha do

    # E. STANDARD CHAT / CODING (Gemini/Groq)
    else:
        if mode == "coding" or vision_object:
            # Use Gemini for Coding or Vision
            if vision_object:
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content([msg, vision_object])
                reply = response.text
            else:
                reply = await generate_gemini(msg + file_text, base_system)
        else:
            # Use Groq for Fast Chat
            client = get_groq()
            if client:
                # Fetch recent history for context
                chat_data = await chats_collection.find_one({"session_id": sid})
                history = chat_data.get("messages", [])[-6:]
                msgs = [{"role": "system", "content": base_system}] + history
                msgs.append({"role": "user", "content": msg + file_text})
                
                completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=msgs)
                reply = completion.choices[0].message.content
            else:
                reply = "⚠️ API Key Error. Check Server Logs."

    # Save Assistant Reply
    await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "assistant", "content": reply}}})
    return {"reply": reply}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)