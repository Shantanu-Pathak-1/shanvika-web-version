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
import PIL.Image 
import random # For Pollinations Seed
from pdf2docx import Converter # New Library for PDF to Word
import tempfile # Temp files for conversion

# ==========================================
# 🔑 KEYS & CONFIG
# ==========================================
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_random_string_shanvika")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# AI Keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN") 
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY") 
MONGO_URL = os.getenv("MONGO_URL")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI()

# 👇 HTTPS LOOP FIX (Render specific)
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
# 🎨 1. SMART IMAGE GENERATION (HF + Backup)
# ==========================================
async def generate_image_hf(prompt):
    # Strategy A: Hugging Face (Best Quality)
    if HF_TOKEN:
        API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-v1-5"
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        
        async with httpx.AsyncClient() as client:
            try:
                # 10s timeout to quickly switch to backup if busy
                response = await client.post(API_URL, headers=headers, json={"inputs": prompt}, timeout=10.0)
                if response.status_code == 200:
                    img_b64 = base64.b64encode(response.content).decode("utf-8")
                    return f"""🎨 **Image (HF):**<br><img src='data:image/png;base64,{img_b64}' class='rounded-lg mt-2 shadow-lg w-full hover:scale-105 transition-transform duration-300'>"""
            except: pass # Silent fail to backup

    # Strategy B: Pollinations AI (Unlimited Free Backup)
    try:
        seed = random.randint(1, 100000)
        safe_prompt = prompt.replace(" ", "%20")
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&seed={seed}&nologo=true"
        return f"""🎨 **Image (Backup):**<br><img src='{image_url}' class='rounded-lg mt-2 shadow-lg w-full hover:scale-105 transition-transform duration-300'>"""
    except Exception as e:
        return f"⚠️ **Failed:** {str(e)}"

# ==========================================
# 🌸 2. ANIME CONVERTER (Prompt Logic)
# ==========================================
async def convert_to_anime(file_data, prompt):
    # Agar user ne file upload ki hai (Img2Img - Not reliable on free tier, avoiding complexity)
    # Hum Smart Logic use karenge: Pollinations URL logic with Anime Prompt
    
    # Simple Text-to-Image Anime (Most Reliable Free Method)
    anime_prompt = f"anime style, studio ghibli, vibrant colors, masterpiece, {prompt}"
    
    # Using Pollinations for Anime (Fastest & Free)
    seed = random.randint(1, 100000)
    safe_prompt = anime_prompt.replace(" ", "%20")
    image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&seed={seed}&model=flux-anime&nologo=true"
    
    return f"""✨ **Anime Art:**<br><img src='{image_url}' class='rounded-lg mt-2 shadow-lg w-full'>"""

# ==========================================
# 🔄 3. UNIVERSAL FILE CONVERTER
# ==========================================
async def perform_conversion(file_data, file_type, prompt):
    try:
        # Decode File
        if "," in file_data: header, encoded = file_data.split(",", 1)
        else: encoded = file_data
        file_bytes = base64.b64decode(encoded)
        
        prompt = prompt.lower()
        target = "pdf"
        if "word" in prompt or "docx" in prompt: target = "docx"
        elif "png" in prompt: target = "png"
        elif "jpg" in prompt: target = "jpeg"

        # A. IMAGE CONVERSION
        if "image" in file_type:
            img = PIL.Image.open(io.BytesIO(file_bytes))
            if target in ["jpeg", "pdf"] and img.mode in ("RGBA", "P"): img = img.convert("RGB")
            
            out = io.BytesIO()
            img.save(out, format=target.upper())
            out_b64 = base64.b64encode(out.getvalue()).decode("utf-8")
            
            mime = "application/pdf" if target == "pdf" else f"image/{target}"
            return f"""✅ **Converted:**<br><a href="data:{mime};base64,{out_b64}" download="converted.{target}" class="inline-block bg-green-600 text-white px-4 py-2 rounded mt-2">Download {target.upper()}</a>"""

        # B. PDF TO WORD
        elif "pdf" in file_type and target == "docx":
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(file_bytes)
                tmp_path = tmp.name
            
            docx_path = tmp_path + ".docx"
            try:
                cv = Converter(tmp_path)
                cv.convert(docx_path, start=0, end=None)
                cv.close()
                
                with open(docx_path, "rb") as f:
                    out_b64 = base64.b64encode(f.read()).decode("utf-8")
                
                return f"""✅ **PDF to Word:**<br><a href="data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,{out_b64}" download="converted.docx" class="inline-block bg-blue-600 text-white px-4 py-2 rounded mt-2">Download Word</a>"""
            except Exception as e: return f"⚠️ Error: {str(e)}"
            finally:
                if os.path.exists(tmp_path): os.remove(tmp_path)
                if os.path.exists(docx_path): os.remove(docx_path)
        
        return "⚠️ Please specify 'convert to pdf/word/png' etc."
    except Exception as e: return f"⚠️ Error: {str(e)}"

# ==========================================
# 🔍 4. RESEARCH & 5. GEMINI (Logic)
# ==========================================
async def perform_research_task(query):
    if TAVILY_API_KEY:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post("https://api.tavily.com/search", json={"api_key": TAVILY_API_KEY, "query": query, "search_depth": "basic", "max_results": 3})
                if resp.status_code == 200:
                    summary = "📊 **Tavily Research:**\n\n"
                    for r in resp.json().get("results", []): summary += f"🔹 **{r['title']}**\n{r['content']}\n🔗 [Link]({r['url']})\n\n"
                    return summary
        except: pass

    try:
        results = DDGS().text(query, max_results=3)
        summary = "📊 **DDG Research:**\n\n"
        for r in results: summary += f"🔹 **{r['title']}**\n{r['body']}\n🔗 {r['href']}\n\n"
        return summary
    except: return "⚠️ Research failed."

async def generate_gemini(prompt, system_instr):
    try:
        model = genai.GenerativeModel('gemini-2.5-flash') 
        return model.generate_content(f"System: {system_instr}\nUser: {prompt}").text
    except:
        model = genai.GenerativeModel('gemini-1.5-flash')
        return model.generate_content(prompt).text

# --- ROUTES & MODELS ---
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
                await users_collection.insert_one({"email": user_info.get('email'), "name": user_info.get('name'), "picture": user_info.get('picture'), "custom_instruction": ""})
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
# 🤖 MAIN CHAT CONTROLLER
# ==========================================
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    user = await get_current_user(request)
    if not user: return {"reply": "⚠️ Please Login first."}

    sid, mode, msg = req.session_id, req.mode, req.message
    
    # 1. FILE PARSING
    file_text = ""
    vision_object = None 
    
    if req.file_data:
        try:
            if "," in req.file_data: header, encoded = req.file_data.split(",", 1)
            else: encoded = req.file_data
            decoded = base64.b64decode(encoded)
            
            # PDF Reading
            if "pdf" in (req.file_type or ""):
                try:
                    reader = PyPDF2.PdfReader(io.BytesIO(decoded))
                    file_text = "\n[PDF CONTENT]:\n" + "\n".join([p.extract_text() for p in reader.pages])
                except: file_text = "[PDF attached but could not be read. Only Conversion available]"
            
            # Image Reading (For Vision)
            elif "image" in (req.file_type or ""):
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
    
    # Update History
    if not await chats_collection.find_one({"session_id": sid}):
        await chats_collection.insert_one({"session_id": sid, "user_email": user['email'], "title": msg[:30], "messages": []})
    await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "user", "content": msg + file_text}}})

    # 3. ROUTING LOGIC
    reply = ""
    
    # A. IMAGE GENERATION
    if mode == "image_gen":
        reply = await generate_image_hf(msg)
        
    # B. FILE CONVERTER (New Mode)
    elif mode == "converter":
        if req.file_data:
            reply = await perform_conversion(req.file_data, req.file_type, msg)
        else:
            reply = "⚠️ **Converter Mode:** Please upload a file (PDF or Image) to convert."

    # C. ANIME CREATOR
    elif mode == "anime":
        reply = await convert_to_anime(req.file_data, msg)

    # D. RESEARCH
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

    # E. STANDARD CHAT (Groq / Gemini)
    else:
        if mode == "coding" or vision_object:
            if vision_object:
                model = genai.GenerativeModel('gemini-2.5-flash')
                response = model.generate_content([msg, vision_object])
                reply = response.text
            else:
                reply = await generate_gemini(msg + file_text, base_system)
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)