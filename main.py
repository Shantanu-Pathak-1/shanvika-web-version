# ==================================================================================
#  FILE: main.py
#  DESCRIPTION: Core Backend Server (FastAPI) handling Chat, Auth, Tools & DB
# ==================================================================================

# [CATEGORY] 1. IMPORTS
from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
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
import json
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
import edge_tts 

# Local Tool Imports
from tools_lab import (
    generate_prompt_only, generate_qr_code, generate_image_hf,
    analyze_resume, review_github, currency_tool,
    summarize_youtube, generate_password_tool, fix_grammar_tool,
    generate_interview_questions, handle_mock_interview,
    solve_math_problem, smart_todo_maker, build_pro_resume,
    sing_with_me_tool 
)

# ==================================================================================
# [CATEGORY] 2. CONFIGURATION & KEYS
# ==================================================================================
ADMIN_EMAIL = "shantanupathak94@gmail.com"
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
MONGO_URL = os.getenv("MONGO_URL")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
MAIL_USERNAME = os.getenv("MAIL_USERNAME") 
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

# ==================================================================================
# [CATEGORY] 3. SYSTEM INTELLIGENCE (Dynamic from JSON)
# ==================================================================================
def load_system_instructions():
    try:
        with open("character_config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            
            # Rules aur Tactics ko list se string banana
            rules_text = "\n".join([f"- {rule}" for rule in config.get("strict_rules", [])])
            tactics_text = "\n".join([f"- {tactic}" for tactic in config.get("psychological_tactics", [])])
            
            # Creator info nikalna
            c_profile = config.get("creator_profile", {})
            
            # Template fill karna
            prompt = config.get("system_prompt_template", "").format(
                name=config["identity"]["name"],
                creator=config["identity"]["creator"],
                rules=rules_text,
                tactics=tactics_text,
                c_name=c_profile.get("name"),
                c_college=c_profile.get("college"),
                c_skills=c_profile.get("skills"),
                c_interests=c_profile.get("interests")
            )
            return prompt
    except Exception as e:
        print(f"Config Load Error: {e}")
        return "You are Shanvika. Always reply in the user's language."

DEFAULT_SYSTEM_INSTRUCTIONS = load_system_instructions()

# ==================================================================================
# [CATEGORY] 4. DATABASE & SECURITY SETUP
# ==================================================================================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pinecone Setup (Vector DB)
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

# MongoDB Setup
client = AsyncIOMotorClient(MONGO_URL)
db = client.shanvika_db
users_collection = db.users
chats_collection = db.chats
otp_collection = db.otps 

# ==================================================================================
# [CATEGORY] 5. APP SETUP (Middleware)
# ==================================================================================
app = FastAPI()

@app.get("/healthz")
async def health_check(): return {"status": "ok"}

# Fix for Google OAuth in Production (HTTPS Proxy)
@app.middleware("http")
async def fix_google_oauth_redirect(request: Request, call_next):
    if request.headers.get("x-forwarded-proto") == "https": request.scope["scheme"] = "https"
    return await call_next(request)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=True, same_site="lax")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Static & Templates
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# OAuth Registry
oauth = OAuth()
oauth.register(name='google', client_id=GOOGLE_CLIENT_ID, client_secret=GOOGLE_CLIENT_SECRET, server_metadata_url='https://accounts.google.com/.well-known/openid-configuration', client_kwargs={'scope': 'openid email profile'})

# ==================================================================================
# [CATEGORY] 6. HELPER FUNCTIONS
# ==================================================================================
def get_random_groq_key():
    keys = os.getenv("GROQ_API_KEY_POOL", "").split(",")
    possible_keys = [k.strip() for k in keys if k.strip()]
    return random.choice(possible_keys) if possible_keys else os.getenv("GROQ_API_KEY")

def get_groq():
    key = get_random_groq_key()
    return Groq(api_key=key) if key else None

def get_random_gemini_key():
    keys = os.getenv("GEMINI_API_KEY_POOL", "").split(",")
    possible_keys = [k.strip() for k in keys if k.strip()]
    return random.choice(possible_keys) if possible_keys else os.getenv("GEMINI_API_KEY")

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

# --- RAG / Memory Helpers ---
def get_embedding(text):
    try:
        key = get_random_gemini_key()
        if key: genai.configure(api_key=key)
        return genai.embed_content(model="models/embedding-001", content=text, task_type="retrieval_document")['embedding']
    except Exception as e:
        print(f"Embedding Error: {e}")
        return []

def search_vector_db(query, user_email):
    if not index: return ""
    vec = get_embedding(query)
    if not vec: return ""
    res = index.query(vector=vec, top_k=3, include_metadata=True, filter={"email": user_email})
    return "\n".join([m['metadata']['text'] for m in res['matches']])

async def perform_research_task(query):
    try: return "📊 **Research:**\n\n" + "\n\n".join([f"🔹 **{r['title']}**\n{r['body']}" for r in DDGS().text(query, max_results=3)])
    except: return "⚠️ Research failed."

# --- NEW: AUTO-MEMORY EXTRACTOR (Background Task) ---
async def extract_and_save_memory(user_email: str, user_message: str):
    """
    Checks if the user message contains important personal info and saves it.
    """
    try:
        # Step 1: Check keywords to save API cost (Optional, but good for speed)
        triggers = ["my name is", "i live in", "i like", "i love", "remember", "save this", "my birthday", "i am", "mera naam", "main rehta hu", "mujhe pasand hai"]
        if not any(t in user_message.lower() for t in triggers) and len(user_message.split()) < 4:
            return # Skip short/irrelevant messages

        # Step 2: Ask LLM to extract facts
        client = get_groq()
        if not client: return

        extraction_prompt = f"""
        Analyze this user message: "{user_message}"
        Extract ANY permanent user fact (Name, Location, Likes, Dislikes, Goals, Relationships).
        Return ONLY the fact as a short sentence. If nothing worth remembering, return 'NO_DATA'.
        Example: "User likes Pizza" or "User lives in Delhi".
        """
        
        # --- FIXED SYNTAX HERE ---
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": extraction_prompt}],
            model="llama-3.3-70b-versatile", # Ensure model name is correct (Llama 3.3 for Groq)
        ).choices[0].message.content.strip()

        if "NO_DATA" not in response and len(response) > 5:
            # Step 3: Save to DB
            clean_memory = response.replace("User", "You").replace("user", "You") # Make it personal
            
            # Save to Mongo
            await users_collection.update_one(
                {"email": user_email},
                {"$push": {"memories": clean_memory}}
            )
            
            # Save to Pinecone (Optional)
            if index:
                vec = get_embedding(clean_memory)
                if vec:
                    mem_id = f"{user_email}_{hashlib.md5(clean_memory.encode()).hexdigest()}"
                    index.upsert(vectors=[(mem_id, vec, {"text": clean_memory, "email": user_email})])
            
            print(f"🧠 Auto-Memory Saved: {clean_memory}")

    except Exception as e:
        print(f"Auto-Memory Error: {e}")

# ==================================================================================
# [CATEGORY] 7. PYDANTIC MODELS
# ==================================================================================
class ChatRequest(BaseModel): message: str; session_id: str; mode: str = "chat"; file_data: str | None = None; file_type: str | None = None
class SignupRequest(BaseModel): email: str; password: str; full_name: str; dob: str; username: str
class OTPRequest(BaseModel): email: str
class OTPVerifyRequest(BaseModel): email: str; otp: str
class LoginRequest(BaseModel): identifier: str; password: str
class ProfileRequest(BaseModel): name: str
class InstructionRequest(BaseModel): instruction: str
class MemoryRequest(BaseModel): memory_text: str
class RenameRequest(BaseModel): session_id: str; new_title: str

# ==================================================================================
# [CATEGORY] 8. AUTH ROUTES
# ==================================================================================
@app.get("/auth/login")
async def login(request: Request):
    redirect_uri = str(request.url_for('auth_callback')).replace("http://", "https://")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user = token.get('userinfo')
        request.session['user'] = user
        await users_collection.update_one(
            {"email": user['email']},
            {"$set": {"name": user.get('name'), "picture": user.get('picture'), "username": user['email'].split('@')[0]}},
            upsert=True
        )
        return RedirectResponse("/")
    except: return RedirectResponse("/login")

@app.get("/logout")
async def logout(request: Request): request.session.pop('user', None); return RedirectResponse("/")

# Manual Auth APIs
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
    await users_collection.insert_one({"email": req.email, "username": req.username, "password_hash": get_password_hash(req.password), "name": req.full_name, "picture": "", "memories": [], "custom_instruction": ""})
    request.session['user'] = {"email": req.email, "name": req.full_name}
    return {"status": "success"}

@app.post("/api/login_manual")
async def login_manual(req: LoginRequest, request: Request):
    user = await users_collection.find_one({"$or": [{"email": req.identifier}, {"username": req.identifier}]})
    if user and verify_password(req.password, user.get('password_hash')):
        request.session['user'] = {"email": user['email'], "name": user['name']}
        return {"status": "success"}
    return JSONResponse({"status": "error"}, 400)

# ==================================================================================
# [CATEGORY] 9. PAGE ROUTES
# ==================================================================================
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request): return templates.TemplateResponse("login.html", {"request": request})

@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request): return templates.TemplateResponse("onboarding.html", {"request": request, "email": "user", "name": "user"})

@app.get("/")
async def read_root(request: Request):
    user = request.session.get('user')
    if user: return templates.TemplateResponse("index.html", {"request": request, "user": user})
    return templates.TemplateResponse("landing.html", {"request": request})

# --- NEW: MEMORY DASHBOARD ROUTE ---
@app.get("/memory-dashboard", response_class=HTMLResponse)
async def memory_dashboard_page(request: Request):
    user = request.session.get('user')
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("memory_dashboard.html", {"request": request, "user": user})

# ==================================================================================
# [CATEGORY] 10. API ROUTES
# ==================================================================================
@app.get("/api/profile")
async def get_profile(request: Request):
    user = await get_current_user(request)
    if not user: return {}
    db_user = await users_collection.find_one({"email": user['email']}) or {}
    is_pro = db_user.get("is_pro", False) or (user['email'] == ADMIN_EMAIL)
    return {
        "name": db_user.get("name") or user.get("name", "User"), 
        "avatar": db_user.get("picture") or user.get("picture"), 
        "plan": "Pro Plan" if is_pro else "Free Plan",
        "custom_instruction": db_user.get("custom_instruction", "") 
    }

@app.post("/api/save_instruction")
async def save_instruction(req: InstructionRequest, request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error", "message": "Login required"}, 400)
    await users_collection.update_one({"email": user['email']}, {"$set": {"custom_instruction": req.instruction}})
    return {"status": "success"}

@app.get("/api/history")
async def get_history(request: Request):
    user = await get_current_user(request)
    if not user: return {"history": []}
    cursor = chats_collection.find({"user_email": user['email']}).sort("_id", -1).limit(50)
    history = []
    async for chat in cursor: history.append({"id": chat["session_id"], "title": chat.get("title", "New Chat")})
    return {"history": history}

@app.get("/api/new_chat")
async def create_chat(request: Request): return {"session_id": str(uuid.uuid4())[:8], "messages": []}

@app.get("/api/chat/{session_id}")
async def get_chat(session_id: str):
    chat = await chats_collection.find_one({"session_id": session_id})
    return {"messages": chat.get("messages", [])} if chat else {"messages": []}

@app.post("/api/rename_chat")
async def rename_chat(req: RenameRequest): return {"status": "ok"}
@app.delete("/api/delete_all_chats")
async def delete_all_chats(request: Request): return {"status": "ok"}

# --- MEMORY API ---
@app.get("/api/memories")
async def get_memories(request: Request):
    user = await get_current_user(request)
    if not user: return {"memories": []}
    data = await users_collection.find_one({"email": user['email']})
    mems = data.get("memories", []) if data else []
    return {"memories": mems[::-1]}

@app.post("/api/add_memory")
async def add_memory(req: MemoryRequest, request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error"}, 400)
    await users_collection.update_one({"email": user['email']}, {"$push": {"memories": req.memory_text}})
    if index:
        try:
            vec = get_embedding(req.memory_text)
            if vec:
                mem_id = f"{user['email']}_{hashlib.md5(req.memory_text.encode()).hexdigest()}"
                index.upsert(vectors=[(mem_id, vec, {"text": req.memory_text, "email": user['email']})])
        except Exception as e: print(f"Vector Save Error: {e}")
    return {"status": "success"}

@app.post("/api/delete_memory")
async def delete_memory(req: MemoryRequest, request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error"}, 400)
    await users_collection.update_one({"email": user['email']}, {"$pull": {"memories": req.memory_text}})
    return {"status": "ok"}

# --------------------------
# CHAT ENDPOINT (AUTO-MEMORY ENABLED)
# --------------------------
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request, background_tasks: BackgroundTasks):
    try:
        user = await get_current_user(request)
        if not user: return {"reply": "⚠️ Login required."}
        
        sid, mode, msg = req.session_id, req.mode, req.message
        
        # --- BACKGROUND TASK: AUTO-MEMORY ---
        # Chat ko slow kiye bina memory extract karo
        if mode == "chat":
            background_tasks.add_task(extract_and_save_memory, user['email'], msg)

        db_user = await users_collection.find_one({"email": user['email']})
        user_custom_prompt = db_user.get("custom_instruction", "")
        
        retrieved_memory = ""
        if index: retrieved_memory = search_vector_db(msg, user['email'])
        if not retrieved_memory:
            recent_mems = db_user.get("memories", [])[-5:]
            if recent_mems: retrieved_memory = "\n".join(recent_mems)

        FINAL_SYSTEM_PROMPT = user_custom_prompt if user_custom_prompt and user_custom_prompt.strip() else DEFAULT_SYSTEM_INSTRUCTIONS
        if retrieved_memory:
            FINAL_SYSTEM_PROMPT += f"\n\n[USER LONG-TERM MEMORY]:\n{retrieved_memory}\n(Use this information to personalize the conversation)"

        chat_doc = await chats_collection.find_one({"session_id": sid})
        if not chat_doc:
            title_prefix = "Chat"
            if mode != "chat": title_prefix = f"Tool: {mode.replace('_', ' ').title()}"
            await chats_collection.insert_one({
                "session_id": sid, "user_email": user['email'], 
                "title": f"{title_prefix} - {msg[:15]}...", "messages": []
            })
            chat_doc = {"messages": []}

        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "user", "content": msg}}})

        reply = ""
        context_history = ""
        if mode == "sing_with_me":
            recent_msgs = chat_doc.get("messages", [])[-4:] 
            for m in recent_msgs: context_history += f"{m['role']}: {m['content']} | "

        # --- TOOL ROUTING ---
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
        
        elif mode == "sing_with_me": reply = await sing_with_me_tool(msg, context_history) 

        elif mode == "research":
            data = await perform_research_task(msg)
            client = get_groq()
            if client: 
                reply = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": FINAL_SYSTEM_PROMPT},
                        {"role": "user", "content": f"Context: {data}\nQ: {msg}"}
                    ], 
                    model="llama-3.3-70b-versatile"
                ).choices[0].message.content
            else: reply = data
        else: # Standard Chat
            client = get_groq()
            if client: 
                full_history = chat_doc.get("messages", []) + [{"role": "user", "content": msg}]
                recent_history = full_history[-15:]
                messages_payload = [{"role": "system", "content": FINAL_SYSTEM_PROMPT}, *recent_history]

                reply = client.chat.completions.create(
                    model="llama-3.3-70b-versatile", 
                    messages=messages_payload
                ).choices[0].message.content
            else: reply = "⚠️ API Error."

        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "assistant", "content": reply}}})
        
        if len(chat_doc['messages']) < 2 and mode != "chat":
             new_title = f"Tool: {mode.replace('_', ' ').title()}"
             await chats_collection.update_one({"session_id": sid}, {"$set": {"title": new_title}})

        return {"reply": reply}

    except Exception as e:
        print(f"ERROR: {e}")
        return {"reply": f"⚠️ Server Error: {str(e)}"}

# Text-to-Speech Endpoint
@app.post("/api/speak")
async def text_to_speech_endpoint(request: Request):
    try:
        data = await request.json()
        text = data.get("text", "")
        text = re.sub(r'<[^>]*>', '', text)
        text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
        clean_text = re.sub(r'[^\w\s\u0900-\u097F,.?!]', '', text) 

        voice = "en-IN-NeerjaNeural" 
        communicate = edge_tts.Communicate(clean_text, voice)
        async def audio_stream():
            async for chunk in communicate.stream():
                if chunk["type"] == "audio": yield chunk["data"]
        return StreamingResponse(audio_stream(), media_type="audio/mp3")
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)