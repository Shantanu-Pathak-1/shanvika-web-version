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
from gradio_client import Client 

# ==========================================
# 🔑 KEYS & CONFIG
# ==========================================
ADMIN_EMAIL = "shantanupathak94@gmail.com"
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_random_string_shanvika")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MONGO_URL = os.getenv("MONGO_URL")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

# 👇 EMAIL CONFIG
MAIL_USERNAME = os.getenv("MAIL_USERNAME") 
BREVO_API_KEY = os.getenv("BREVO_API_KEY")

# Password Hashing
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

if GEMINI_API_KEY:
    try: genai.configure(api_key=GEMINI_API_KEY)
    except: pass

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

# --- HELPERS ---
def get_groq(): return Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
async def get_current_user(request: Request): return request.session.get('user')

# 👇 SECURITY LOGIC (SHA-256 PRE-HASHING)
def verify_password(plain_password, hashed_password):
    if not plain_password or not hashed_password: return False
    sha_signature = hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.verify(sha_signature, hashed_password)

def get_password_hash(password):
    print(f"🔒 Processing Password: {password[:5]}***") 
    sha_signature = hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.hash(sha_signature)

# 👇 BREVO API EMAIL FUNCTION (PORT 443 SAFE)
def send_email(to_email: str, subject: str, body: str):
    api_key = os.getenv("BREVO_API_KEY") 
    sender_email = os.getenv("MAIL_USERNAME") 
    
    if not api_key:
        print("❌ ERROR: BREVO_API_KEY missing in Env!")
        return False

    url = "https://api.brevo.com/v3/smtp/email"
    
    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }
    
    payload = {
        "sender": {"email": sender_email, "name": "Shanvika AI"},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": body
    }
    
    try:
        response = httpx.post(url, headers=headers, json=payload)
        if response.status_code == 201:
            print("✅ Email sent via Brevo API!")
            return True
        else:
            print(f"❌ Email Failed: {response.text}")
            return False
    except Exception as e:
        print(f"❌ API Connection Error: {e}")
        return False

# ==========================================
# 🎨 SMART GENERATORS (Prompt Writer + Flux + Anime)
# ==========================================

# 1. Prompt Enhancer (Gemini)
async def improve_prompt(user_text):
    try:
        if not user_text: return "A masterpiece"
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = (
            f"You are an expert AI Art Prompter. Rewrite this simple prompt into a highly detailed, "
            f"descriptive prompt for an AI image generator. "
            f"Focus on lighting, camera angle, texture, and mood. Keep it under 40 words. "
            f"Input: '{user_text}'"
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except:
        return user_text 

# 2. Pro Image Generator (Flux Realism)
async def generate_image_hf(user_prompt):
    try:
        final_prompt = await improve_prompt(user_prompt)
        print(f"✨ Enhanced Prompt: {final_prompt}")

        seed = random.randint(1, 1000000)
        safe_prompt = final_prompt.replace(" ", "%20")
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&seed={seed}&model=flux&nologo=true"
        
        return f"""
        <div class="glass p-2 rounded-lg mt-2">
            <p class="text-xs text-gray-400 mb-1">Generating: {final_prompt[:40]}...</p>
            <img src='{image_url}' class='rounded-lg shadow-lg w-full transition hover:scale-105' onload="this.scrollIntoView({{behavior: 'smooth', block: 'center'}})">
            <a href="{image_url}" target="_blank" class="block text-center text-pink-500 text-xs mt-2 hover:underline">Download HD</a>
        </div>
        """
    except Exception as e: return f"⚠️ Image Error: {str(e)}"

# 3. Anime Generator (Qwen Model - Face Match)
# 👇 3. ANIME GENERATOR (Safe & Smart Version)
async def generate_anime_qwen(img_data, user_prompt):
    try:
        if "," in img_data: header, encoded = img_data.split(",", 1)
        else: encoded = img_data
        decoded = base64.b64decode(encoded)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp.write(decoded)
            tmp_path = tmp.name

        print("🚀 Connecting to Qwen Anime Space...")
        
        # 👇 YAHAN HAI MAGIC FIX
        # Hum check karenge ki library token leti hai ya nahi
        token = os.getenv("HF_TOKEN")
        space_id = "prithivMLmods/Qwen-Image-Edit-2509-LoRAs-Fast"
        
        try:
            # Pehle Token ke sath try karo (Fast Lane)
            client = Client(space_id, hf_token=token)
            print("✅ Connected with HF Token!")
        except TypeError:
            # Agar purani library hai, toh bina token ke connect karo (Standard Lane)
            print("⚠️ Old Gradio Client detected. Connecting without token...")
            client = Client(space_id)

        result = client.predict(
            image=tmp_path,
            prompt=user_prompt or "Turn this into anime style",
            adapter_choice="Photo-to-Anime", 
            seed=random.randint(1, 9999),
            guidance_scale=7.5,
            steps=30,
            api_name="/run_image_edit"
        )
        
        output_path = result[0]
        with open(output_path, "rb") as f:
            out_b64 = base64.b64encode(f.read()).decode("utf-8")
            
        return f"""
        <div class="glass p-2 rounded-lg mt-2">
            <p class="text-xs text-pink-400 font-bold mb-1">✨ Anime Version Ready!</p>
            <img src='data:image/jpeg;base64,{out_b64}' class='rounded-lg shadow-lg w-full'>
            <a href="data:image/jpeg;base64,{out_b64}" download="anime_shanvika.jpg" class="block text-center text-white text-xs mt-2 bg-pink-600 px-2 py-1 rounded">Download</a>
        </div>
        """
    except Exception as e:
        print(f"Anime Error: {e}")
        # Error ko user-friendly banaya
        return f"⚠️ Anime Server Busy. Please try again in 1 minute. (Error: {str(e)[:50]}...)"

# ... (Standard Converters & Research) ...
async def perform_conversion(file_data, file_type, prompt):
    try:
        if "," in file_data: header, encoded = file_data.split(",", 1)
        else: encoded = file_data
        file_bytes = base64.b64decode(encoded)
        prompt = prompt.lower()
        target = "pdf"
        if "word" in prompt or "docx" in prompt: target = "docx"
        elif "png" in prompt: target = "png"
        elif "jpg" in prompt: target = "jpeg"
        elif "webp" in prompt: target = "webp"
        should_compress = "compress" in prompt or "size" in prompt
        
        if "image" in file_type:
            img = PIL.Image.open(io.BytesIO(file_bytes))
            if img.mode in ("RGBA", "P") and target in ["jpeg", "pdf"]: img = img.convert("RGB")
            out = io.BytesIO()
            if should_compress:
                img.save(out, format=target.upper(), optimize=True, quality=30)
                msg_text = "✅ **Compressed!**"
            else:
                img.save(out, format=target.upper(), quality=95)
                msg_text = f"✅ **Converted to {target.upper()}!**"
            out_b64 = base64.b64encode(out.getvalue()).decode("utf-8")
            mime = "application/pdf" if target == "pdf" else f"image/{target}"
            return f"""{msg_text}<br><a href="data:{mime};base64,{out_b64}" download="converted.{target}" class="inline-block bg-green-600 text-white px-4 py-2 rounded mt-2">Download File</a>"""
        
        elif "pdf" in file_type and target == "docx":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            docx_path = tmp_path + ".docx"
            try:
                cv = Converter(tmp_path)
                cv.convert(docx_path, start=0, end=None)
                cv.close()
                with open(docx_path, "rb") as f: out_b64 = base64.b64encode(f.read()).decode("utf-8")
                return f"""✅ **PDF to Word:**<br><a href="data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{out_b64}" download="converted.docx" class="inline-block bg-blue-600 text-white px-4 py-2 rounded mt-2">Download Word</a>"""
            except Exception as e: return f"⚠️ Error: {str(e)}"
            finally:
                if os.path.exists(tmp_path): os.remove(tmp_path)
                if os.path.exists(docx_path): os.remove(docx_path)
        return "⚠️ Specify format."
    except Exception as e: return f"⚠️ Error: {str(e)}"

async def perform_research_task(query):
    try:
        results = DDGS().text(query, max_results=3)
        summary = "📊 **Research:**\n\n"
        for r in results: summary += f"🔹 **{r['title']}**\n{r['body']}\n🔗 {r['href']}\n\n"
        return summary
    except: return "⚠️ Research failed."

async def generate_gemini(prompt, system_instr):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash') 
        return model.generate_content(f"System: {system_instr}\nUser: {prompt}").text
    except: return "⚠️ Gemini Error."

# ... (RAG Functions) ...
def get_embedding(text):
    try:
        result = genai.embed_content(
            model="models/embedding-001",
            content=text,
            task_type="retrieval_document",
            title="Shanvika Memory"
        )
        return result['embedding']
    except Exception as e:
        print(f"Embedding Error: {e}")
        return []

def split_text(text, chunk_size=500):
    words = text.split()
    chunks = []
    current_chunk = []
    current_size = 0
    for word in words:
        current_chunk.append(word)
        current_size += len(word) + 1
        if current_size >= chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_size = 0
    if current_chunk: chunks.append(" ".join(current_chunk))
    return chunks

def save_to_vector_db(session_id, text):
    if not index: return False
    chunks = split_text(text)
    vectors = []
    for i, chunk in enumerate(chunks):
        vector = get_embedding(chunk)
        if vector:
            vectors.append({
                "id": f"{session_id}_{i}",
                "values": vector,
                "metadata": {"text": chunk, "session_id": session_id}
            })
    if vectors:
        index.upsert(vectors=vectors)
        return True
    return False

def search_vector_db(query, session_id):
    if not index: return ""
    query_vector = get_embedding(query)
    if not query_vector: return ""
    results = index.query(
        vector=query_vector,
        top_k=3,
        include_metadata=True,
        filter={"session_id": session_id}
    )
    context = ""
    for match in results['matches']:
        context += match['metadata']['text'] + "\n\n"
    return context

# --- STANDARD ROUTES ---
class ChatRequest(BaseModel):
    message: str
    session_id: str
    mode: str = "chat"
    file_data: str | None = None
    file_type: str | None = None

class RenameRequest(BaseModel):
    session_id: str
    new_title: str

class ProfileRequest(BaseModel):
    name: str

class InstructionRequest(BaseModel):
    instruction: str

class MemoryRequest(BaseModel):
    memory_text: str

# 👇 AUTH MODELS
class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: str
    dob: str
    username: str

class OTPRequest(BaseModel):
    email: str

class OTPVerifyRequest(BaseModel):
    email: str
    otp: str

class LoginRequest(BaseModel):
    identifier: str
    password: str

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request): return templates.TemplateResponse("login.html", {"request": request})

@app.get("/auth/login")
async def login(request: Request):
    redirect_uri = str(request.url_for('auth_callback'))
    if "onrender.com" in redirect_uri: redirect_uri = redirect_uri.replace("http://", "https://")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse("/login")
    return templates.TemplateResponse("onboarding.html", {"request": request, "email": user['email'], "name": user.get('name', '')})

# 👇 API ROUTES FOR AUTH
@app.post("/api/send_otp")
async def send_otp_endpoint(req: OTPRequest):
    if await users_collection.find_one({"email": req.email}):
        return JSONResponse({"status": "error", "message": "Email already registered! Please Login."}, status_code=400)
    
    otp = str(random.randint(100000, 999999))
    await otp_collection.update_one(
        {"email": req.email}, 
        {"$set": {"otp": otp, "created_at": datetime.utcnow()}}, 
        upsert=True
    )
    
    email_body = f"""
    <div style="font-family: Arial, sans-serif; color: #333;">
        <h2>Welcome to Shanvika AI 🌸</h2>
        <p>Your verification code is:</p>
        <h1 style="color: #ec4899; letter-spacing: 5px;">{otp}</h1>
        <p>This code is valid for 10 minutes.</p>
    </div>
    """
    
    if send_email(req.email, "Shanvika AI - Verification Code", email_body):
        return {"status": "success", "message": "OTP sent to email!"}
    return JSONResponse({"status": "error", "message": "Failed to send email. Check API Key."}, status_code=500)

@app.post("/api/verify_otp")
async def verify_otp_endpoint(req: OTPVerifyRequest):
    record = await otp_collection.find_one({"email": req.email})
    if record and record.get("otp") == req.otp:
        await otp_collection.delete_one({"email": req.email}) 
        return {"status": "success"}
    return JSONResponse({"status": "error", "message": "Invalid OTP"}, status_code=400)

@app.post("/api/complete_signup")
async def complete_signup(req: SignupRequest, request: Request):
    try:
        if await users_collection.find_one({"username": req.username}):
            return JSONResponse({"status": "error", "message": "Username taken!"}, status_code=400)
            
        hashed_pass = get_password_hash(req.password)
        
        new_user = {
            "email": req.email,
            "name": req.full_name,
            "username": req.username,
            "dob": req.dob,
            "password_hash": hashed_pass,
            "picture": f"https://ui-avatars.com/api/?name={req.full_name}&background=random",
            "custom_instruction": "",
            "memories": [],
            "gallery": [],
            "is_banned": False,
            "is_pro": False,
            "joined_at": datetime.utcnow()
        }
        
        await users_collection.insert_one(new_user)
        
        request.session['user'] = {
            "email": new_user['email'], 
            "name": new_user['name'], 
            "picture": new_user['picture'],
            "username": new_user['username']
        }
        return {"status": "success"}
    except Exception as e:
        print(f"SIGNUP ERROR: {e}")
        return JSONResponse({"status": "error", "message": f"Server Error: {str(e)}"}, status_code=500)

@app.post("/api/login_manual")
async def login_manual(req: LoginRequest, request: Request):
    user = await users_collection.find_one({
        "$or": [{"email": req.identifier}, {"username": req.identifier}]
    })
    
    if not user or not user.get('password_hash'):
        return JSONResponse({"status": "error", "message": "User not found or uses Google Login"}, status_code=400)
    
    if verify_password(req.password, user['password_hash']):
        request.session['user'] = {
            "email": user['email'], 
            "name": user['name'], 
            "picture": user['picture'],
            "username": user.get('username')
        }
        return {"status": "success"}
    
    return JSONResponse({"status": "error", "message": "Invalid Password"}, status_code=400)

@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        if user_info:
            email = user_info.get('email')
            db_user = await users_collection.find_one({"email": email})
            
            if not db_user:
                request.session['user'] = dict(user_info) 
                return RedirectResponse(url="/onboarding") 
            elif "username" not in db_user:
                 request.session['user'] = dict(user_info)
                 return RedirectResponse(url="/onboarding")

            request.session['user'] = {
                "email": db_user['email'],
                "name": db_user['name'],
                "picture": db_user['picture'],
                "username": db_user.get('username')
            }
        return RedirectResponse(url="/")
    except Exception as e:
        print(e)
        return RedirectResponse(url="/login")

@app.post("/api/complete_google_onboarding")
async def complete_google_onboarding(request: Request):
    data = await request.json()
    user = await get_current_user(request)
    if not user: return JSONResponse({"status": "error"}, status_code=401)
    await users_collection.update_one({"email": user['email']}, {"$set": {"dob": data.get("dob"), "username": data.get("username")}}, upsert=True)
    if not await users_collection.find_one({"email": user['email']}):
         await users_collection.insert_one({"email": user['email'], "name": user.get('name'), "picture": user.get('picture'), "dob": data.get("dob"), "username": data.get("username"), "custom_instruction": "", "memories": [], "gallery": [], "is_banned": False})
    return {"status": "success"}

@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request): return templates.TemplateResponse("about.html", {"request": request})

@app.get("/gallery", response_class=HTMLResponse)
async def gallery_page(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse(url="/")
    db_user = await users_collection.find_one({"email": user['email']})
    images = db_user.get("gallery", [])
    return templates.TemplateResponse("gallery.html", {"request": request, "images": reversed(images)})

@app.post("/api/delete_gallery_item")
async def delete_gallery_item(request: Request):
    user = await get_current_user(request)
    data = await request.json()
    await users_collection.update_one({"email": user['email']}, {"$pull": {"gallery": {"url": data.get("url")}}})
    return {"status": "ok"}

@app.get("/logout")
async def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse(url="/")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    user = await get_current_user(request)
    if user: return templates.TemplateResponse("index.html", {"request": request, "user": user})
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/api/profile")
async def get_profile(request: Request):
    user = await get_current_user(request)
    if not user: return {}
    db_user = await users_collection.find_one({"email": user['email']})
    is_pro = db_user.get("is_pro", False) or (user['email'] == ADMIN_EMAIL)
    return {"name": db_user.get("name"), "avatar": db_user.get("picture"), "custom_instruction": db_user.get("custom_instruction", ""), "plan": "Pro Plan" if is_pro else "Free Plan"}

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

@app.delete("/api/delete_all_chats")
async def delete_all_chats(request: Request):
    user = await get_current_user(request)
    if user: await chats_collection.delete_many({"user_email": user['email']})
    return {"status": "ok"}

@app.get("/api/memories")
async def get_memories(request: Request):
    user = await get_current_user(request)
    if not user: return {"memories": []}
    db_user = await users_collection.find_one({"email": user['email']})
    return {"memories": db_user.get("memories", [])}

@app.post("/api/add_memory")
async def add_memory(req: MemoryRequest, request: Request):
    user = await get_current_user(request)
    if user: await users_collection.update_one({"email": user['email']}, {"$push": {"memories": req.memory_text}})
    return {"status": "ok"}

@app.post("/api/delete_memory")
async def delete_memory(req: MemoryRequest, request: Request):
    user = await get_current_user(request)
    if user: await users_collection.update_one({"email": user['email']}, {"$pull": {"memories": req.memory_text}})
    return {"status": "ok"}

@app.post("/api/upgrade_plan")
async def upgrade_plan(request: Request):
    user = await get_current_user(request)
    if not user: return JSONResponse({"error": "Login required"}, status_code=401)
    await users_collection.update_one({"email": user['email']}, {"$set": {"plan_type": "pro", "is_pro": True}})
    return {"status": "success", "message": "Plan Upgraded to Pro!"}

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    user = await get_current_user(request)
    if not user or user['email'] != ADMIN_EMAIL: return RedirectResponse(url="/")
    users_cursor = users_collection.find()
    users_list = []
    banned_count = 0
    async for u in users_cursor:
        msg_count = await chats_collection.count_documents({"user_email": u['email']})
        u['msg_count'] = msg_count
        if u.get('is_banned', False): banned_count += 1
        users_list.append(u)
    total_users = len(users_list)
    total_chats = await chats_collection.count_documents({})
    return templates.TemplateResponse("admin.html", {"request": request, "users": users_list, "total_users": total_users, "total_chats": total_chats, "banned_count": banned_count, "admin_email": ADMIN_EMAIL})

@app.post("/admin/ban_user")
async def ban_user(request: Request, email: str = Form(...)):
    user = await get_current_user(request)
    if not user or user['email'] != ADMIN_EMAIL: return JSONResponse({"error": "Unauthorized"}, status_code=403)
    await users_collection.update_one({"email": email}, {"$set": {"is_banned": True}})
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/unban_user")
async def unban_user(request: Request, email: str = Form(...)):
    user = await get_current_user(request)
    if not user or user['email'] != ADMIN_EMAIL: return JSONResponse({"error": "Unauthorized"}, status_code=403)
    await users_collection.update_one({"email": email}, {"$set": {"is_banned": False}})
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/promote_user")
async def promote_user(request: Request, email: str = Form(...)):
    user = await get_current_user(request)
    if not user or user['email'] != ADMIN_EMAIL: return JSONResponse({"error": "Unauthorized"}, status_code=403)
    await users_collection.update_one({"email": email}, {"$set": {"is_pro": True, "plan_type": "pro"}})
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/demote_user")
async def demote_user(request: Request, email: str = Form(...)):
    user = await get_current_user(request)
    if not user or user['email'] != ADMIN_EMAIL: return JSONResponse({"error": "Unauthorized"}, status_code=403)
    await users_collection.update_one({"email": email}, {"$set": {"is_pro": False, "plan_type": "free"}})
    return RedirectResponse(url="/admin", status_code=303)

# ==========================================
# 🤖 CHAT ROUTER
# ==========================================
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    try:
        user = await get_current_user(request)
        if not user: return {"reply": "⚠️ Please Login first."}
        
        db_user_check = await users_collection.find_one({"email": user['email']})
        if db_user_check.get("is_banned", False):
            return {"reply": "🚫 **ACCOUNT SUSPENDED**"}

        sid, mode, msg = req.session_id, req.mode, req.message
        
        file_text = ""
        vision_object = None
        if req.file_data:
            try:
                if "," in req.file_data: header, encoded = req.file_data.split(",", 1)
                else: encoded = req.file_data
                decoded = base64.b64decode(encoded)
                if "pdf" in (req.file_type or ""):
                    try:
                        reader = PyPDF2.PdfReader(io.BytesIO(decoded))
                        raw_text = "\n".join([p.extract_text() for p in reader.pages])
                        save_to_vector_db(sid, raw_text)
                        file_text = " [System: PDF content saved]"
                    except: file_text = "[PDF attached]"
                elif "image" in (req.file_type or "") and mode != "anime":
                    vision_object = PIL.Image.open(io.BytesIO(decoded))
                    msg += " [Image Attached]"
            except Exception as e: return {"reply": f"⚠️ File Error: {e}"}

        custom_instr = db_user_check.get("custom_instruction", "")
        memories = db_user_check.get("memories", [])
        base_system = "You are Shanvika AI."
        if custom_instr: base_system += f"\nUser Settings: {custom_instr}"
        if memories:
            base_system += "\n\n[USER MEMORIES]:\n"
            for m in memories: base_system += f"- {m}\n"
        if mode == "coding": base_system += " You are an Expert Coder."
        
        if not await chats_collection.find_one({"session_id": sid}):
            await chats_collection.insert_one({"session_id": sid, "user_email": user['email'], "title": msg[:30], "messages": []})
        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "user", "content": msg + file_text}}})

        reply = ""
        
        # 🔥 UPDATED ROUTING LOGIC 🔥
        if mode == "image_gen":
            reply = await generate_image_hf(msg)

        elif mode == "anime":
            if req.file_data:
                reply = await generate_anime_qwen(req.file_data, msg)
            else:
                prompt = await improve_prompt(msg + " in anime style")
                reply = await generate_image_hf(prompt)

        elif mode == "converter":
            if req.file_data: reply = await perform_conversion(req.file_data, req.file_type, msg)
            else: reply = "⚠️ Upload file to convert."

        elif mode == "research":
            research_data = await perform_research_task(msg)
            client = get_groq()
            if client:
                completion = client.chat.completions.create(messages=[{"role": "system", "content": base_system}, {"role": "user", "content": f"Data: {research_data}\nQuery: {msg}\nSummarize."}], model="llama-3.3-70b-versatile")
                reply = completion.choices[0].message.content
            else: reply = research_data

        else:
            if mode == "coding" or vision_object:
                if vision_object:
                    model = genai.GenerativeModel('gemini-2.5-flash')
                    response = model.generate_content([msg, vision_object])
                    reply = response.text
                else: reply = await generate_gemini(msg + file_text, base_system)
            else:
                client = get_groq()
                if client:
                    context_data = search_vector_db(msg, sid)
                    system_prompt = base_system
                    if context_data: system_prompt += f"\n\n[RELEVANT INFO]:\n{context_data}"
                    chat_data = await chats_collection.find_one({"session_id": sid})
                    history = chat_data.get("messages", [])[-6:]
                    msgs = [{"role": "system", "content": system_prompt}] + history
                    msgs.append({"role": "user", "content": msg}) 
                    completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=msgs)
                    reply = completion.choices[0].message.content
                else: reply = "⚠️ API Error."

        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "assistant", "content": reply}}})
        
        # Save to gallery if image generated
        if "src=" in reply and "img" in reply:
             try:
                url_match = re.search(r"src='([^']+)'", reply)
                if url_match:
                    img_url = url_match.group(1)
                    await users_collection.update_one({"email": user['email']}, {"$push": {"gallery": {"url": img_url, "prompt": msg, "mode": mode}}})
             except: pass

        return {"reply": reply}
    except Exception as e:
        print(f"ERROR: {e}")
        return {"reply": f"⚠️ **Server Error:** {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)