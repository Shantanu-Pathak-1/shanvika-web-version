from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, HTTPException, status
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
import httpx 
import base64 
from groq import Groq
from duckduckgo_search import DDGS
import google.generativeai as genai 
import io
import PyPDF2
from docx import Document
import PIL.Image 
import random 
import re 
from pdf2docx import Converter 
import tempfile 
from pinecone import Pinecone, ServerlessSpec
import numpy as np
import hashlib 
from passlib.context import CryptContext
from datetime import datetime
import qrcode 

# ==========================================
# 🔑 KEYS & CONFIG
# ==========================================
ADMIN_EMAIL = "shantanupathak94@gmail.com"
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_random_string_shanvika")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
MONGO_URL = os.getenv("MONGO_URL")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
MAIL_USERNAME = os.getenv("MAIL_USERNAME") 
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 👇 Initialize Pinecone
pc = None
index = None
try:
    if PINECONE_API_KEY:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index_name = "shanvika-memory"
        existing_indexes = pc.list_indexes().names()
        if index_name not in existing_indexes:
            try:
                pc.create_index(
                    name=index_name,
                    dimension=768,
                    metric='cosine',
                    spec=ServerlessSpec(cloud='aws', region='us-east-1')
                )
            except: pass
        index = pc.Index(index_name)
except Exception as e:
    print(f"Pinecone Error: {e}")

app = FastAPI()

# Health Check
@app.get("/healthz")
async def health_check():
    return {"status": "ok", "message": "Shanvika is running!"}

# HTTPS Fix
@app.middleware("http")
async def fix_google_oauth_redirect(request: Request, call_next):
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"
    response = await call_next(request)
    return response

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=True, same_site="lax")
oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# DB Setup
client = AsyncIOMotorClient(MONGO_URL)
db = client.shanvika_db
users_collection = db.users
chats_collection = db.chats
otp_collection = db.otps 

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ==========================================
# 🔄 KEY ROTATION LOGIC (LOAD BALANCER)
# ==========================================
def get_random_groq_key():
    keys_str = os.getenv("GROQ_API_KEY_POOL", "")
    if not keys_str: return os.getenv("GROQ_API_KEY")
    keys_list = [k.strip() for k in keys_str.split(",") if k.strip()]
    return random.choice(keys_list) if keys_list else None

def get_random_gemini_key():
    keys_str = os.getenv("GEMINI_API_KEY_POOL", "")
    if not keys_str: return os.getenv("GEMINI_API_KEY")
    keys_list = [k.strip() for k in keys_str.split(",") if k.strip()]
    return random.choice(keys_list) if keys_list else None

# --- HELPERS ---
def get_groq():
    api_key = get_random_groq_key()
    return Groq(api_key=api_key) if api_key else None

async def get_current_user(request: Request): return request.session.get('user')

def verify_password(plain_password, hashed_password):
    if not plain_password or not hashed_password: return False
    sha_signature = hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.verify(sha_signature, hashed_password)

def get_password_hash(password):
    sha_signature = hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.hash(sha_signature)

def send_email(to_email: str, subject: str, body: str):
    api_key = os.getenv("BREVO_API_KEY") 
    sender_email = os.getenv("MAIL_USERNAME") 
    if not api_key: return False
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {"accept": "application/json", "api-key": api_key, "content-type": "application/json"}
    payload = {"sender": {"email": sender_email, "name": "Shanvika AI"}, "to": [{"email": to_email}], "subject": subject, "htmlContent": body}
    try:
        response = httpx.post(url, headers=headers, json=payload)
        return response.status_code == 201
    except: return False

# ==========================================
# 🛠️ UTILITY TOOLS (The New "Experiments")
# ==========================================

# 1. PROMPT WRITER (Returns Text)
async def generate_prompt_only(user_text):
    try:
        api_key = get_random_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = (
            f"Act as a professional Midjourney/Flux Prompt Engineer. "
            f"Write a highly detailed, creative prompt based on this input: '{user_text}'. "
            f"Include style, lighting, camera settings, and resolution. Output ONLY the prompt text."
        )
        response = model.generate_content(prompt)
        final_text = response.text.strip()
        
        return f"""
        <div class="glass p-4 rounded-xl border border-pink-500/30">
            <h3 class="text-sm font-bold text-pink-400 mb-2">✨ Professional Prompt:</h3>
            <div class="bg-black/40 p-3 rounded-lg text-gray-300 text-sm italic mb-3 select-all">
                {final_text}
            </div>
            <p class="text-[10px] text-gray-500">Copy this and use it in any Image Generator.</p>
        </div>
        """
    except Exception as e: return f"⚠️ Error generating prompt: {str(e)}"

# 2. QR CODE GENERATOR (Offline & Fast)
async def generate_qr_code(data):
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        return f"""
        <div class="glass p-4 rounded-xl text-center">
            <h3 class="text-sm font-bold text-white mb-2">📱 Your QR Code</h3>
            <img src="data:image/png;base64,{img_str}" class="mx-auto rounded-lg shadow-lg w-48 h-48">
            <p class="text-xs text-gray-400 mt-2">Scan or Download</p>
            <a href="data:image/png;base64,{img_str}" download="shanvika_qr.png" class="inline-block mt-2 bg-white text-black px-4 py-1 rounded text-xs font-bold hover:bg-gray-200">Download PNG</a>
        </div>
        """
    except Exception as e: return f"⚠️ QR Error: {str(e)}"

# 3. IMAGE GENERATOR (Internal Helper)
async def generate_image_hf(user_prompt):
    try:
        # Prompt enhancer internal
        api_key = get_random_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        enhancement = model.generate_content(f"Refine this art prompt for Flux Realism (under 30 words): {user_prompt}").text
        
        seed = random.randint(1, 1000000)
        safe_prompt = enhancement.replace(" ", "%20")
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&seed={seed}&model=flux&nologo=true"
        return f"""<div class="glass p-2 rounded-lg mt-2"><img src='{image_url}' class='rounded-lg shadow-lg w-full'><a href="{image_url}" target="_blank" class="block text-center text-pink-500 text-xs mt-2 hover:underline">Download HD</a></div>"""
    except: return "⚠️ Image Gen Failed."

# --- RAG & SYSTEM FUNCTIONS (Standard) ---
def get_embedding(text):
    try:
        api_key = get_random_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        result = genai.embed_content(model="models/embedding-001", content=text, task_type="retrieval_document", title="Shanvika Memory")
        return result['embedding']
    except: return []

def search_vector_db(query, session_id):
    if not index: return ""
    query_vector = get_embedding(query)
    if not query_vector: return ""
    results = index.query(vector=query_vector, top_k=3, include_metadata=True, filter={"session_id": session_id})
    context = ""
    for match in results['matches']: context += match['metadata']['text'] + "\n\n"
    return context

def save_to_vector_db(session_id, text): return True 

async def perform_conversion(file_data, file_type, prompt):
    return "⚠️ Conversion logic placeholder (add full logic if needed)"

async def perform_research_task(query):
    try:
        results = DDGS().text(query, max_results=3)
        summary = "📊 **Research:**\n\n"
        for r in results: summary += f"🔹 **{r['title']}**\n{r['body']}\n🔗 {r['href']}\n\n"
        return summary
    except: return "⚠️ Research failed."

async def generate_gemini(prompt, system_instr):
    try:
        api_key = get_random_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash') 
        return model.generate_content(f"System: {system_instr}\nUser: {prompt}").text
    except: return "⚠️ Gemini Error."

# ... (Models & Auth Routes) ...
class ChatRequest(BaseModel): message: str; session_id: str; mode: str = "chat"; file_data: str | None = None; file_type: str | None = None
class SignupRequest(BaseModel): email: str; password: str; full_name: str; dob: str; username: str
class OTPRequest(BaseModel): email: str
class OTPVerifyRequest(BaseModel): email: str; otp: str
class LoginRequest(BaseModel): identifier: str; password: str
class ProfileRequest(BaseModel): name: str
class InstructionRequest(BaseModel): instruction: str
class MemoryRequest(BaseModel): memory_text: str
class RenameRequest(BaseModel): session_id: str; new_title: str

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request): return templates.TemplateResponse("login.html", {"request": request})
@app.get("/auth/login")
async def login(request: Request): return await oauth.google.authorize_redirect(request, str(request.url_for('auth_callback')).replace("http://", "https://"))
@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request): return templates.TemplateResponse("onboarding.html", {"request": request, "email": "user", "name": "user"})
@app.post("/api/guest_login")
async def guest_login(request: Request):
    request.session['user'] = {"email": f"guest_{uuid.uuid4()}@shanvika.ai", "name": "Guest", "picture": "", "is_guest": True}
    return {"status": "success"}
@app.post("/api/send_otp")
async def send_otp_endpoint(req: OTPRequest):
    if await users_collection.find_one({"email": req.email}): return JSONResponse({"status": "error", "message": "Exists!"}, 400)
    otp = str(random.randint(100000, 999999))
    await otp_collection.update_one({"email": req.email}, {"$set": {"otp": otp}}, upsert=True)
    if send_email(req.email, "Code", f"<h1>{otp}</h1>"): return {"status": "success"}
    return JSONResponse({"status": "error"}, 500)
@app.post("/api/verify_otp")
async def verify_otp_endpoint(req: OTPVerifyRequest):
    record = await otp_collection.find_one({"email": req.email})
    if record and record.get("otp") == req.otp: return {"status": "success"}
    return JSONResponse({"status": "error"}, 400)
@app.post("/api/complete_signup")
async def complete_signup(req: SignupRequest, request: Request):
    if await users_collection.find_one({"username": req.username}): return JSONResponse({"status": "error"}, 400)
    await users_collection.insert_one({"email": req.email, "username": req.username, "password_hash": get_password_hash(req.password), "name": req.full_name, "picture": "", "memories": []})
    request.session['user'] = {"email": req.email, "name": req.full_name}
    return {"status": "success"}
@app.post("/api/login_manual")
async def login_manual(req: LoginRequest, request: Request):
    user = await users_collection.find_one({"$or": [{"email": req.identifier}, {"username": req.identifier}]})
    if user and verify_password(req.password, user.get('password_hash')):
        request.session['user'] = {"email": user['email'], "name": user['name']}
        return {"status": "success"}
    return JSONResponse({"status": "error"}, 400)
@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user = token.get('userinfo')
        request.session['user'] = user
        return RedirectResponse("/")
    except: return RedirectResponse("/login")
@app.get("/logout")
async def logout(request: Request): request.session.pop('user', None); return RedirectResponse("/")
@app.get("/")
async def read_root(request: Request): return templates.TemplateResponse("index.html", {"request": request, "user": request.session.get('user')})
@app.get("/api/profile")
async def get_profile(request: Request):
    user = await get_current_user(request)
    if not user: return {}
    if user.get('is_guest'): return {"name": "Guest", "avatar": user['picture'], "plan": "Guest Mode"}
    db_user = await users_collection.find_one({"email": user['email']})
    is_pro = db_user.get("is_pro", False) or (user['email'] == ADMIN_EMAIL)
    return {"name": db_user.get("name"), "avatar": db_user.get("picture"), "custom_instruction": db_user.get("custom_instruction", ""), "plan": "Pro Plan" if is_pro else "Free Plan"}
@app.get("/api/history")
async def get_history(request: Request): return {"history": []} 
@app.get("/api/new_chat")
async def create_chat(request: Request): return {"session_id": str(uuid.uuid4())[:8], "messages": []}
@app.get("/api/chat/{session_id}")
async def get_chat(session_id: str): return {"messages": []}
@app.post("/api/rename_chat")
async def rename_chat(req: RenameRequest): return {"status": "ok"}
@app.delete("/api/delete_all_chats")
async def delete_all_chats(request: Request): return {"status": "ok"}
@app.get("/api/memories")
async def get_memories(request: Request): return {"memories": []}
@app.post("/api/add_memory")
async def add_memory(req: MemoryRequest): return {"status": "ok"}
@app.post("/api/delete_memory")
async def delete_memory(req: MemoryRequest): return {"status": "ok"}

# ==========================================
# 🤖 CHAT CONTROLLER
# ==========================================
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    try:
        user = await get_current_user(request)
        if not user: return {"reply": "⚠️ Please Login first."}
        
        sid, mode, msg = req.session_id, req.mode, req.message
        
        if not await chats_collection.find_one({"session_id": sid}):
            await chats_collection.insert_one({"session_id": sid, "user_email": user['email'], "title": msg[:30], "messages": []})
        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "user", "content": msg}}})

        reply = ""
        
        # 🔥🔥🔥 UTILITY TOOLS LOGIC 🔥🔥🔥
        if mode == "image_gen":
            reply = await generate_image_hf(msg)
        elif mode == "prompt_writer":
            reply = await generate_prompt_only(msg)
        elif mode == "qr_generator":
            reply = await generate_qr_code(msg)
        elif mode == "converter":
            reply = "⚠️ Converter logic placeholder"
        elif mode == "research":
            research_data = await perform_research_task(msg)
            client = get_groq()
            if client:
                completion = client.chat.completions.create(messages=[{"role": "system", "content": "You are Shanvika."}, {"role": "user", "content": f"Data: {research_data}\nQuery: {msg}\nSummarize."}], model="llama-3.3-70b-versatile")
                reply = completion.choices[0].message.content
            else: reply = research_data
        else:
            client = get_groq()
            if client:
                completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": msg}])
                reply = completion.choices[0].message.content
            else: reply = "⚠️ API Error."

        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "assistant", "content": reply}}})
        return {"reply": reply}

    except Exception as e:
        print(f"ERROR: {e}")
        return {"reply": f"⚠️ **Server Error:** {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)