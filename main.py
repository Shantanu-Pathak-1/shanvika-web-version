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
import edge_tts # 👈 NEW
from fastapi.responses import StreamingResponse # 👈 NEW
# ... baaki purane imports same rahenge

# 👇 IMPORT ALL 15 TOOLS
from tools_lab import (
    generate_prompt_only, generate_qr_code, generate_image_hf,
    analyze_resume, review_github, currency_tool,
    summarize_youtube, generate_password_tool, fix_grammar_tool,
    generate_interview_questions, handle_mock_interview,
    solve_math_problem, smart_todo_maker, build_pro_resume,
    sing_with_me_tool # 👈 New
)

# ==========================================
# 🔑 KEYS & CONFIG
# ==========================================
ADMIN_EMAIL = "shantanupathak94@gmail.com"
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
MONGO_URL = os.getenv("MONGO_URL")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
MAIL_USERNAME = os.getenv("MAIL_USERNAME") 
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

pc = None
index = None
try:
    if PINECONE_API_KEY:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        index_name = "shanvika-memory"
        existing_indexes = pc.list_indexes().names()
        if index_name not in existing_indexes:
            try: pc.create_index(name=index_name, dimension=768, metric='cosine', spec=ServerlessSpec(cloud='aws', region='us-east-1'))
            except: pass
        index = pc.Index(index_name)
except: pass

app = FastAPI()

@app.get("/healthz")
async def health_check(): return {"status": "ok"}

@app.middleware("http")
async def fix_google_oauth_redirect(request: Request, call_next):
    if request.headers.get("x-forwarded-proto") == "https": request.scope["scheme"] = "https"
    return await call_next(request)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=True, same_site="lax")
oauth = OAuth()
oauth.register(name='google', client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET, server_metadata_url='https://accounts.google.com/.well-known/openid-configuration', client_kwargs={'scope': 'openid email profile'})

client = AsyncIOMotorClient(MONGO_URL)
db = client.shanvika_db
users_collection = db.users
chats_collection = db.chats
otp_collection = db.otps 

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- HELPERS ---
def get_random_groq_key():
    keys = os.getenv("GROQ_API_KEY_POOL", "").split(",")
    return random.choice([k.strip() for k in keys if k.strip()]) or os.getenv("GROQ_API_KEY")

def get_groq():
    key = get_random_groq_key()
    return Groq(api_key=key) if key else None

async def get_current_user(request: Request): return request.session.get('user')
def verify_password(plain, hashed): return pwd_context.verify(hashlib.sha256(plain.encode()).hexdigest(), hashed) if plain and hashed else False
def get_password_hash(password): return pwd_context.hash(hashlib.sha256(password.encode()).hexdigest())

def send_email(to, subject, body):
    api = os.getenv("BREVO_API_KEY")
    if not api: return False
    try:
        httpx.post("https://api.brevo.com/v3/smtp/email", headers={"api-key": api, "content-type": "application/json"}, json={"sender": {"email": os.getenv("MAIL_USERNAME"), "name": "Shanvika"}, "to": [{"email": to}], "subject": subject, "htmlContent": body})
        return True
    except: return False

# --- RAG ---
def get_embedding(text):
    try:
        key = os.getenv("GEMINI_API_KEY")
        if key: genai.configure(api_key=key)
        return genai.embed_content(model="models/embedding-001", content=text, task_type="retrieval_document")['embedding']
    except: return []

def search_vector_db(query, session_id):
    if not index: return ""
    vec = get_embedding(query)
    if not vec: return ""
    res = index.query(vector=vec, top_k=3, include_metadata=True, filter={"session_id": session_id})
    return "\n".join([m['metadata']['text'] for m in res['matches']])

async def perform_research_task(query):
    try: return "📊 **Research:**\n\n" + "\n\n".join([f"🔹 **{r['title']}**\n{r['body']}" for r in DDGS().text(query, max_results=3)])
    except: return "⚠️ Research failed."

# --- ROUTES ---
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
    db_user = await users_collection.find_one({"email": user['email']}) or {}
    is_pro = db_user.get("is_pro", False) or (user['email'] == ADMIN_EMAIL)
    return {"name": db_user.get("name", "User"), "avatar": db_user.get("picture"), "plan": "Pro Plan" if is_pro else "Free Plan"}
# main.py ke andar is function ko dhoondo aur replace kar do:

@app.get("/api/history")
async def get_history(request: Request):
    user = await get_current_user(request)
    if not user: return {"history": []}
    
    # Database se chats nikalo (Newest first)
    cursor = chats_collection.find({"user_email": user['email']}).sort("_id", -1).limit(50)
    history = []
    async for chat in cursor:
        history.append({
            "id": chat["session_id"],
            "title": chat.get("title", "New Chat")
        })
    return {"history": history}
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
# 🤖 CHAT ROUTER
# ==========================================
# main.py ke andar 'chat_endpoint' function ko isse replace karo:

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    try:
        user = await get_current_user(request)
        if not user: return {"reply": "⚠️ Login required."}
        
        sid, mode, msg = req.session_id, req.mode, req.message
        
        # 1️⃣ HISTORY CHECK & CREATE
        chat_doc = await chats_collection.find_one({"session_id": sid})
        if not chat_doc:
            # New chat title based on Mode
            title_prefix = "Chat"
            if mode != "chat": title_prefix = f"Tool: {mode.replace('_', ' ').title()}"
            
            await chats_collection.insert_one({
                "session_id": sid, 
                "user_email": user['email'], 
                "title": f"{title_prefix} - {msg[:15]}...", # Better Title
                "messages": []
            })
            chat_doc = {"messages": []} # Empty for now

        # 2️⃣ SAVE USER MESSAGE
        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "user", "content": msg}}})

        reply = ""
        
        # 3️⃣ PREPARE CONTEXT (For Singing Mode)
        context_history = ""
        if mode == "sing_with_me":
            # Pichle 4 messages uthao taaki AI ko song ka context yaad rahe
            recent_msgs = chat_doc.get("messages", [])[-4:] 
            for m in recent_msgs:
                context_history += f"{m['role']}: {m['content']} | "

        # 4️⃣ TOOLS ROUTING
        if mode == "image_gen": reply = await generate_image_hf(msg)
        elif mode == "prompt_writer": reply = await generate_prompt_only(msg)
        elif mode == "qr_generator": reply = await generate_qr_code(msg)
        elif mode == "resume_analyzer": reply = await analyze_resume(req.file_data, msg)
        elif mode == "github_review": reply = await review_github(msg)
        elif mode == "currency_converter": reply = await currency_tool(msg)
        elif mode == "youtube_summarizer": reply = await summarize_youtube(msg)
        elif mode == "password_generator": reply = await generate_password_tool(msg)
        elif mode == "grammar_fixer": reply = await fix_grammar_tool(msg)
        elif mode == "interview_questions": reply = await generate_interview_questions(msg)
        elif mode == "mock_interviewer": reply = await handle_mock_interview(msg)
        elif mode == "math_solver": reply = await solve_math_problem(req.file_data, msg)
        elif mode == "smart_todo": reply = await smart_todo_maker(msg)
        elif mode == "resume_builder": reply = await build_pro_resume(msg)
        
        # 👇 Updated Call with Context
        elif mode == "sing_with_me": 
            reply = await sing_with_me_tool(msg, context_history) 

        elif mode == "research":
            data = await perform_research_task(msg)
            client = get_groq()
            if client: reply = client.chat.completions.create(messages=[{"role": "system", "content": "You are Shanvika."}, {"role": "user", "content": f"Context: {data}\nQ: {msg}"}], model="llama-3.3-70b-versatile").choices[0].message.content
            else: reply = data
        else: # Chat/Coding
            client = get_groq()
            if client: reply = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": msg}]).choices[0].message.content
            else: reply = "⚠️ API Error."

        # 5️⃣ SAVE AI REPLY (CRITICAL FOR HISTORY)
        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "assistant", "content": reply}}})
        
        # 6️⃣ OPTIONAL: Update Title if it was generic "New Chat"
        if len(chat_doc['messages']) < 2 and mode != "chat":
             new_title = f"Tool: {mode.replace('_', ' ').title()}"
             await chats_collection.update_one({"session_id": sid}, {"$set": {"title": new_title}})

        return {"reply": reply}

    except Exception as e:
        print(f"ERROR: {e}")
        return {"reply": f"⚠️ Server Error: {str(e)}"}
    
    # ==========================================
# 🗣️ VOICE SYSTEM (Edge TTS - Free & Human Like)
# ==========================================
@app.post("/api/speak")
async def text_to_speech_endpoint(request: Request):
    try:
        data = await request.json()
        text = data.get("text", "")
        
        # Emoji aur symbols hatao taaki voice clean rahe
        clean_text = re.sub(r'[*#_`]', '', text) 
        
        # 🗣️ VOICE SELECTION
        # "en-IN-NeerjaNeural" = Best Indian English Female Voice
        # "hi-IN-SwaraNeural" = Best Hindi Female Voice
        voice = "en-IN-NeerjaNeural" 
        
        # Communicate object create karo
        communicate = edge_tts.Communicate(clean_text, voice)
        
        # Audio Stream Generate karo
        async def audio_stream():
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]

        return StreamingResponse(audio_stream(), media_type="audio/mp3")

    except Exception as e:
        print(f"TTS Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)