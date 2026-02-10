from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
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

app = FastAPI()

# ==========================================
# 🔑 KEYS & CONFIG (SECRET RAKHNA)
# ==========================================

# 1. Google & Security Keys
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_random_string_shanvika") # Session ke liye
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "PASTE_YOUR_CLIENT_ID_HERE_IF_LOCAL")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "PASTE_YOUR_CLIENT_SECRET_HERE_IF_LOCAL")

# 2. AI & DB Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
MONGO_URL = os.getenv("MONGO_URL") # MongoDB Connection String

# 3. Setup Session (Zaroori hai login yaad rakhne ke liye)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# 4. Setup Google OAuth
oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# 5. Connect to MongoDB
client = AsyncIOMotorClient(MONGO_URL)
db = client.shanvika_db  # Database Name
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
def get_deepseek(): return OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com") if DEEPSEEK_API_KEY else None

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
# 🚀 AUTH ROUTES (Login/Logout)
# ==========================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/auth/login")
async def login(request: Request):
    # Determine callback URL based on environment (Local vs Render)
    redirect_uri = str(request.url_for('auth_callback'))
    # Fix for Render (Ensure HTTPS)
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
            
            # Save User to MongoDB if not exists
            email = user_info.get('email')
            existing_user = await users_collection.find_one({"email": email})
            
            if not existing_user:
                await users_collection.insert_one({
                    "email": email,
                    "name": user_info.get('name'),
                    "picture": user_info.get('picture'),
                    "role": "user" # Default role
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
# 💬 APP ROUTES (Protected)
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    user = await get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/api/profile")
async def get_profile(request: Request):
    user = await get_current_user(request)
    if not user: return {"name": "Guest", "avatar": ""}
    
    # Fetch latest data from DB
    db_user = await users_collection.find_one({"email": user['email']})
    
    return {
        "name": db_user.get("name", user['name']),
        "avatar": db_user.get("picture", user['picture']),
        "email": user['email']
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

@app.get("/api/history")
async def get_history(request: Request):
    user = await get_current_user(request)
    if not user: return {"history": []}
    
    # Fetch chats ONLY for this user from MongoDB
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
    # Create empty chat in DB
    await chats_collection.insert_one({
        "session_id": new_id,
        "user_email": user['email'],
        "title": "New Chat",
        "messages": []
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
    
    # Fetch Chat from DB
    chat = await chats_collection.find_one({"session_id": sid, "user_email": user['email']})
    
    if not chat:
        # Emergency creation if not found
        chat = {"session_id": sid, "user_email": user['email'], "title": "New Chat", "messages": []}
        await chats_collection.insert_one(chat)
    
    # Update Title if first message
    if len(chat["messages"]) == 0:
        new_title = " ".join(msg.split()[:5])
        await chats_collection.update_one({"session_id": sid}, {"$set": {"title": new_title}})

    user_content = msg
    if img_data: user_content += " [🖼️ Image Uploaded]"
    
    # Add User Message to DB
    await chats_collection.update_one(
        {"session_id": sid},
        {"$push": {"messages": {"role": "user", "content": user_content}}}
    )

    reply = ""
    try:
        # ... (SAME AI LOGIC AS BEFORE) ...
        if mode == "image_gen":
            reply = await generate_image_hf(msg)

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
                    # Pass previous messages (History context)
                    msgs.extend(chat["messages"][-10:])
                    completion = client.chat.completions.create(model=model, messages=msgs)
                    reply = completion.choices[0].message.content
                else: reply = "⚠️ API Key missing."

    except Exception as e:
        reply = f"⚠️ Error: {str(e)}"
        print(f"Error Log: {e}")

    # Save Assistant Reply to DB
    await chats_collection.update_one(
        {"session_id": sid},
        {"$push": {"messages": {"role": "assistant", "content": reply}}}
    )
    
    return {"reply": reply}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)