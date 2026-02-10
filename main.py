from fastapi import FastAPI, Request, UploadFile, File, Form
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
from pdf2docx import Converter 
import tempfile 

# ==========================================
# 🔑 KEYS & CONFIG
# ==========================================
ADMIN_EMAIL = "shantanupathak94@gmail.com"

SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_random_string_shanvika")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# AI Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY") 
MONGO_URL = os.getenv("MONGO_URL")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI()

# 👇 HTTPS LOOP FIX
@app.middleware("http")
async def fix_google_oauth_redirect(request: Request, call_next):
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"
    response = await call_next(request)
    return response

# Session & OAuth
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=True, same_site="lax")
oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# DB & Static
client = AsyncIOMotorClient(MONGO_URL)
db = client.shanvika_db
users_collection = db.users
chats_collection = db.chats

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- HELPER FUNCTIONS ---
def get_groq(): return Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
async def get_current_user(request: Request): return request.session.get('user')

# ==========================================
# 🧠 MEMORY MANAGEMENT ROUTES (NEW)
# ==========================================
class MemoryRequest(BaseModel):
    memory_text: str

@app.get("/api/memories")
async def get_memories(request: Request):
    user = await get_current_user(request)
    if not user: return {"memories": []}
    db_user = await users_collection.find_one({"email": user['email']})
    return {"memories": db_user.get("memories", [])}

@app.post("/api/add_memory")
async def add_memory(req: MemoryRequest, request: Request):
    user = await get_current_user(request)
    if user: 
        await users_collection.update_one(
            {"email": user['email']}, 
            {"$push": {"memories": req.memory_text}}
        )
    return {"status": "ok"}

@app.post("/api/delete_memory")
async def delete_memory(req: MemoryRequest, request: Request):
    user = await get_current_user(request)
    if user:
        await users_collection.update_one(
            {"email": user['email']},
            {"$pull": {"memories": req.memory_text}}
        )
    return {"status": "ok"}

@app.delete("/api/delete_all_chats")
async def delete_all_chats(request: Request):
    user = await get_current_user(request)
    if user:
        await chats_collection.delete_many({"user_email": user['email']})
    return {"status": "ok"}

# ==========================================
# 🎨 GENERATORS (Image/Anime/Converter)
# ==========================================
async def generate_image_hf(prompt):
    try:
        seed = random.randint(1, 100000)
        safe_prompt = prompt.replace(" ", "%20")
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&seed={seed}&model=flux&nologo=true"
        return f"""🎨 **Painting (Flux):**<br><img src='{image_url}' class='rounded-lg mt-2 shadow-lg w-full hover:scale-105 transition-transform duration-300'>"""
    except Exception as e: return f"⚠️ Error: {str(e)}"

async def convert_to_anime(file_data, prompt):
    try:
        anime_prompt = f"anime style, studio ghibli, highly detailed, {prompt}"
        seed = random.randint(1, 100000)
        safe_prompt = anime_prompt.replace(" ", "%20")
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&seed={seed}&model=flux&nologo=true"
        return f"""✨ **Anime Art:**<br><img src='{image_url}' class='rounded-lg mt-2 shadow-lg w-full'>"""
    except Exception as e: return f"⚠️ Error: {str(e)}"

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
        
        return "⚠️ Specify format (png, jpg, pdf, word)."
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
            if not await users_collection.find_one({"email": user_info.get('email')}):
                await users_collection.insert_one({"email": user_info.get('email'), "name": user_info.get('name'), "picture": user_info.get('picture'), "custom_instruction": "", "memories": []})
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
# 👑 ADMIN PANEL
# ==========================================
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    user = await get_current_user(request)
    if not user or user['email'] != ADMIN_EMAIL:
        return RedirectResponse(url="/")
    
    all_users = await users_collection.find().to_list(length=1000)
    total_users = await users_collection.count_documents({})
    total_chats = await chats_collection.count_documents({})
    
    return templates.TemplateResponse("admin.html", {
        "request": request, "users": all_users, "total_users": total_users, "total_chats": total_chats, "admin_email": ADMIN_EMAIL
    })

@app.post("/admin/delete_user")
async def delete_user(request: Request, email: str = Form(...)):
    user = await get_current_user(request)
    if not user or user['email'] != ADMIN_EMAIL: return JSONResponse({"error": "Unauthorized"}, status_code=403)
    await users_collection.delete_one({"email": email})
    await chats_collection.delete_many({"user_email": email})
    return RedirectResponse(url="/admin", status_code=303)

# ==========================================
# 🤖 CHAT CONTROLLER (With Memory Injection)
# ==========================================
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    try:
        user = await get_current_user(request)
        if not user: return {"reply": "⚠️ Please Login first."}
        sid, mode, msg = req.session_id, req.mode, req.message
        
        # 1. File Handling
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
                        file_text = "\n[PDF]:\n" + "\n".join([p.extract_text() for p in reader.pages])
                    except: file_text = "[PDF attached]"
                elif "image" in (req.file_type or ""):
                    vision_object = PIL.Image.open(io.BytesIO(decoded))
                    msg += " [Image Attached]"
            except Exception as e: return {"reply": f"⚠️ File Error: {e}"}

        # 2. PROMPT ENGINEERING (Injecting Memory)
        db_user = await users_collection.find_one({"email": user['email']})
        custom_instr = db_user.get("custom_instruction", "")
        memories = db_user.get("memories", [])
        
        base_system = "You are Shanvika AI."
        if custom_instr: base_system += f"\nUser Settings: {custom_instr}"
        
        # Inject Memories
        if memories:
            base_system += "\n\n[USER MEMORIES (Remember these facts)]:\n"
            for m in memories: base_system += f"- {m}\n"

        if mode == "coding": base_system += " You are an Expert Coder."
        
        # DB Updates
        if not await chats_collection.find_one({"session_id": sid}):
            await chats_collection.insert_one({"session_id": sid, "user_email": user['email'], "title": msg[:30], "messages": []})
        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "user", "content": msg + file_text}}})

        # 3. ROUTING
        reply = ""
        if mode == "image_gen": reply = await generate_image_hf(msg)
        elif mode == "converter":
            if req.file_data: reply = await perform_conversion(req.file_data, req.file_type, msg)
            else: reply = "⚠️ Upload file to convert."
        elif mode == "anime": reply = await convert_to_anime(req.file_data, msg)
        elif mode == "research":
            research_data = await perform_research_task(msg)
            client = get_groq()
            if client:
                completion = client.chat.completions.create(
                    messages=[{"role": "system", "content": base_system}, {"role": "user", "content": f"Data: {research_data}\nQuery: {msg}\nSummarize."}],
                    model="llama-3.3-70b-versatile"
                )
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
                    chat_data = await chats_collection.find_one({"session_id": sid})
                    history = chat_data.get("messages", [])[-6:]
                    msgs = [{"role": "system", "content": base_system}] + history
                    msgs.append({"role": "user", "content": msg + file_text})
                    completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=msgs)
                    reply = completion.choices[0].message.content
                else: reply = "⚠️ API Error."

        await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "assistant", "content": reply}}})
        return {"reply": reply}

    except Exception as e:
        print(f"ERROR: {e}")
        return {"reply": f"⚠️ **Server Error:** {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)