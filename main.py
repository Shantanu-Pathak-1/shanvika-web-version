from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from authlib.integrations.starlette_client import OAuth
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorClient # MongoDB
import asyncio
import uuid
import shutil
import os
import httpx
from groq import Groq
from openai import OpenAI
from duckduckgo_search import DDGS
import google.generativeai as genai  # 👈 New Import for Gemini

app = FastAPI()

# 👇👇👇 HTTPS LOOP FIX 👇👇👇
@app.middleware("http")
async def fix_google_oauth_redirect(request: Request, call_next):
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"
    response = await call_next(request)
    return response

# ==========================================
# 🔑 KEYS & CONFIG
# ==========================================
ADMIN_EMAIL = "shantanupathak94@gmail.com"

# 1. Google & Security Keys
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_random_string_shanvika")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# 2. AI & DB Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
MONGO_URL = os.getenv("MONGO_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # 👈 Gemini Key

# 3. Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# 4. Setup Session
app.add_middleware(
    SessionMiddleware, 
    secret_key=SECRET_KEY, 
    https_only=True,   
    same_site="lax"    
)

# 5. Setup Google OAuth
oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# 6. Connect to MongoDB
client = AsyncIOMotorClient(MONGO_URL)
db = client.shanvika_db
users_collection = db.users
chats_collection = db.chats

# ==========================================
# ⚙️ STANDARD SETUP
# ==========================================

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- AI CLIENTS ---
def get_groq(): return Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# --- NEW: GEMINI GENERATOR ---
async def generate_gemini(prompt, system_instr):
    try:
        # Gemini 1.5 Flash (Fast & Free)
        model = genai.GenerativeModel('gemini-1.5-flash')
        # Combine system instruction with user prompt
        full_prompt = f"System Instruction: {system_instr}\n\nUser Query: {prompt}"
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Gemini Error: {str(e)}"

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

class InstructionRequest(BaseModel): # 👈 New Model for Custom Instructions
    instruction: str

# --- HELPER FUNCTIONS ---
async def get_current_user(request: Request):
    user = request.session.get('user')
    if user: return user
    return None

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

# ==========================================
# 🚀 AUTH ROUTES
# ==========================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/auth/login")
async def login(request: Request):
    redirect_uri = str(request.url_for('auth_callback'))
    if "onrender.com" in redirect_uri:
        redirect_uri = redirect_uri.replace("http://", "https://")
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        
        if user_info:
            request.session['user'] = dict(user_info)
            email = user_info.get('email')
            existing_user = await users_collection.find_one({"email": email})
            
            if not existing_user:
                await users_collection.insert_one({
                    "email": email,
                    "name": user_info.get('name'),
                    "picture": user_info.get('picture'),
                    "role": "user",
                    "custom_instruction": "" # 👈 New field init
                })
                
        return RedirectResponse(url="/")
    except Exception as e:
        print(f"Auth Error: {e}")
        return RedirectResponse(url="/login")

@app.get("/logout")
async def logout(request: Request):
    request.session.pop('user', None)
    return RedirectResponse(url="/login")

# ==========================================
# 💬 APP ROUTES & API
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse(url="/login")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/api/profile")
async def get_profile(request: Request):
    user = await get_current_user(request)
    if not user: return {"name": "Guest", "avatar": ""}
    
    db_user = await users_collection.find_one({"email": user['email']})
    
    return {
        "name": db_user.get("name", user['name']),
        "avatar": db_user.get("picture", user['picture']),
        "email": user['email'],
        "custom_instruction": db_user.get("custom_instruction", "") # 👈 Send to frontend
    }

@app.post("/api/update_profile_name")
async def update_profile_name(req: ProfileRequest, request: Request):
    user = await get_current_user(request)
    if user:
        await users_collection.update_one(
            {"email": user['email']},
            {"$set": {"name": req.name}}
        )
    return {"status": "success"}

@app.post("/api/update_instructions")
async def update_instructions(req: InstructionRequest, request: Request):
    user = await get_current_user(request)
    if user:
        # Save instruction (Limit to 1000 chars safe side)
        await users_collection.update_one(
            {"email": user['email']},
            {"$set": {"custom_instruction": req.instruction[:1000]}}
        )
    return {"status": "success"}

@app.get("/api/history")
async def get_history(request: Request):
    user = await get_current_user(request)
    if not user: return {"history": []}
    cursor = chats_collection.find({"user_email": user['email']})
    history = []
    async for chat in cursor:
        history.append({"id": chat["session_id"], "title": chat.get("title", "New Chat")})
    return {"history": list(reversed(history))}

@app.get("/api/new_chat")
async def create_chat(request: Request):
    user = await get_current_user(request)
    if not user: return {"error": "Not logged in"}
    new_id = str(uuid.uuid4())[:8]
    await chats_collection.insert_one({
        "session_id": new_id, "user_email": user['email'], "title": "New Chat", "messages": []
    })
    return {"session_id": new_id, "messages": []}

@app.get("/api/chat/{session_id}")
async def get_chat_content(session_id: str, request: Request):
    user = await get_current_user(request)
    if not user: return {"messages": []}
    chat = await chats_collection.find_one({"session_id": session_id, "user_email": user['email']})
    return {"messages": chat.get("messages", []) if chat else []}

@app.post("/api/rename_chat")
async def rename_chat(req: RenameRequest, request: Request):
    user = await get_current_user(request)
    if user:
        await chats_collection.update_one(
            {"session_id": req.session_id, "user_email": user['email']},
            {"$set": {"title": req.new_title}}
        )
    return {"status": "success"}

@app.delete("/api/delete_chat/{session_id}")
async def delete_chat_endpoint(session_id: str, request: Request):
    user = await get_current_user(request)
    if user:
        await chats_collection.delete_one({"session_id": session_id, "user_email": user['email']})
    return {"status": "success"}

# --- MAIN CHAT LOGIC ---
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    user = await get_current_user(request)
    if not user: return {"reply": "⚠️ Please Login first."}

    sid = req.session_id
    mode = req.mode
    msg = req.message
    img_data = req.image 
    
    # 1. Fetch User Data (Custom Instructions)
    db_user = await users_collection.find_one({"email": user['email']})
    custom_instr = db_user.get("custom_instruction", "") if db_user else ""

    # 2. Build Base System Prompt
    base_system = "You are Shanvika AI."
    if custom_instr:
        base_system += f"\n\nIMPORTANT USER INSTRUCTION (Follow this personality/language):\n{custom_instr}\n\n"

    # 3. Add Mode Specifics
    if mode == "coding": base_system += " You are an Expert Coder. Write clean, bug-free code."
    elif mode == "anime": base_system += " You are an Anime Expert (Otaku)."
    elif mode == "video": base_system += " You are a Script Writer."
    
    # Fetch/Create Chat
    chat = await chats_collection.find_one({"session_id": sid, "user_email": user['email']})
    if not chat:
        chat = {"session_id": sid, "user_email": user['email'], "title": "New Chat", "messages": []}
        await chats_collection.insert_one(chat)
    
    if len(chat["messages"]) == 0:
        await chats_collection.update_one({"session_id": sid}, {"$set": {"title": msg[:30]}})

    user_content = msg
    if img_data: user_content += " [🖼️ Image Uploaded]"
    
    await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "user", "content": user_content}}})

    reply = ""
    try:
        # --- AI ROUTING ---
        if mode == "image_gen":
            reply = await generate_image_hf(msg)

        elif mode == "coding":
            # ⚡ Use Gemini for Coding
            reply = await generate_gemini(msg, base_system)

        elif mode == "research":
            research_data = await asyncio.to_thread(perform_research, msg)
            client = get_groq()
            if research_data and client:
                completion = client.chat.completions.create(
                    messages=[{"role": "system", "content": base_system}, {"role": "user", "content": f"Data: {research_data}\nQuery: {msg}"}],
                    model="llama-3.3-70b-versatile"
                )
                reply = completion.choices[0].message.content
            else: reply = research_data if research_data else "⚠️ No results."

        else:
            # Default Chat (Groq) with Custom Instructions
            if img_data:
                client = get_groq()
                if client:
                    completion = client.chat.completions.create(
                        model="llama-3.2-11b-vision-preview",
                        messages=[{"role": "user", "content": [{"type": "text", "text": f"{base_system}\nQuery: {msg}"}, {"type": "image_url", "image_url": {"url": img_data}}]}]
                    )
                    reply = completion.choices[0].message.content
                else: reply = "⚠️ Groq Key missing."
            else:
                client = get_groq()
                if client:
                    msgs = [{"role": "system", "content": base_system}] # Base system has custom instructions now
                    msgs.extend(chat["messages"][-10:])
                    completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=msgs)
                    reply = completion.choices[0].message.content
                else: reply = "⚠️ API Key missing."

    except Exception as e:
        reply = f"⚠️ Error: {str(e)}"
        print(f"Error Log: {e}")

    await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "assistant", "content": reply}}})
    return {"reply": reply}

# ==========================================
# 👑 ADMIN PANEL ROUTES
# ==========================================

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    user = await get_current_user(request)
    if not user: return RedirectResponse(url="/login")
    
    if user['email'] != ADMIN_EMAIL:
        return HTMLResponse("<h1>🚫 Access Denied! Sirf Shantanu (Admin) yahan aa sakta hai.</h1>", status_code=403)

    all_users = await users_collection.find().to_list(length=100)
    total_chats = await chats_collection.count_documents({})
    
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "users": all_users, 
        "total_users": len(all_users),
        "total_chats": total_chats,
        "admin_email": ADMIN_EMAIL
    })

@app.post("/admin/delete_user")
async def delete_user(request: Request):
    user = await get_current_user(request)
    if not user or user['email'] != ADMIN_EMAIL:
        return {"error": "Unauthorized"}
    
    form = await request.form()
    target_email = form.get("email")
    if target_email:
        await users_collection.delete_one({"email": target_email})
        await chats_collection.delete_many({"user_email": target_email})
    return RedirectResponse(url="/admin", status_code=303)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)