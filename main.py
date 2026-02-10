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
import httpx 
import base64 
from groq import Groq
from duckduckgo_search import DDGS
import google.generativeai as genai
import io
import PyPDF2
from docx import Document
import PIL.Image 

app = FastAPI()

@app.middleware("http")
async def fix_google_oauth_redirect(request: Request, call_next):
    if request.headers.get("x-forwarded-proto") == "https":
        request.scope["scheme"] = "https"
    response = await call_next(request)
    return response

# CONFIG
ADMIN_EMAIL = "shantanupathak94@gmail.com"
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_random_string_shanvika")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
HF_TOKEN = os.getenv("HF_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=True, same_site="lax")

oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

client = AsyncIOMotorClient(MONGO_URL)
db = client.shanvika_db
users_collection = db.users
chats_collection = db.chats

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
if not os.path.exists("static"): os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# HELPERS
def get_groq(): return Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
async def get_current_user(request: Request):
    return request.session.get('user')

async def generate_gemini(prompt, system_instr):
    try:
        model = genai.GenerativeModel('gemini-1.5-flash') 
        full_prompt = f"System Instruction: {system_instr}\n\nUser Query: {prompt}"
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"⚠️ Gemini Error: {str(e)}"

def perform_research(query):
    try:
        results = DDGS().text(query, max_results=5)
        if not results: return None
        summary = "📊 **Web Research Results:**\n\n"
        for i, r in enumerate(results, 1):
            summary += f"**{i}. {r['title']}**\n{r['body']}\n🔗 Source: {r['href']}\n\n"
        return summary
    except Exception as e:
        return f"Research Error: {e}"

async def generate_image_hf(prompt):
    if not HF_TOKEN: return "⚠️ Error: HF_TOKEN missing."
    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(API_URL, headers=headers, json={"inputs": prompt}, timeout=30.0)
        if response.status_code == 200:
            img_b64 = base64.b64encode(response.content).decode("utf-8")
            return f"""<div class="mt-2"><img src='data:image/png;base64,{img_b64}' class='rounded-lg shadow-lg w-full max-w-md'></div>"""
        else: return f"⚠️ Image Failed: {response.text[:200]}"
    except Exception as e: return f"⚠️ Error: {str(e)}"

async def generate_video_hf(prompt):
    if not HF_TOKEN: return "⚠️ Error: HF_TOKEN missing."
    API_URL = "https://api-inference.huggingface.co/models/damo-vilab/text-to-video-ms-1.7b"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(API_URL, headers=headers, json={"inputs": prompt}, timeout=60.0)
        if response.status_code == 200:
            vid_b64 = base64.b64encode(response.content).decode("utf-8")
            return f"""<div class="mt-2"><video controls autoplay loop class='rounded-lg shadow-lg w-full max-w-md'><source src='data:video/mp4;base64,{vid_b64}' type='video/mp4'></video></div>"""
        else: return f"⚠️ Video Failed: {response.text[:200]}"
    except Exception as e: return f"⚠️ Error: {str(e)}"

# MODELS & ROUTES
class ChatRequest(BaseModel):
    message: str
    session_id: str
    mode: str
    file_data: str | None = None 
    file_type: str | None = None 
    image: str | None = None 

class RenameRequest(BaseModel):
    session_id: str
    new_title: str

class ProfileRequest(BaseModel):
    name: str

class InstructionRequest(BaseModel):
    instruction: str

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
                    "email": email, "name": user_info.get('name'), 
                    "picture": user_info.get('picture'), "role": "user", "custom_instruction": ""
                })
        return RedirectResponse(url="/")
    except Exception as e:
        print(f"Auth Error: {e}")
        return RedirectResponse(url="/login")

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
    if not user: return {"name": "Guest", "avatar": ""}
    db_user = await users_collection.find_one({"email": user['email']})
    return {"name": db_user.get("name", user['name']), "avatar": db_user.get("picture", user['picture']), 
            "email": user['email'], "custom_instruction": db_user.get("custom_instruction", "")}

@app.post("/api/update_profile_name")
async def update_profile_name(req: ProfileRequest, request: Request):
    user = await get_current_user(request)
    if user: await users_collection.update_one({"email": user['email']}, {"$set": {"name": req.name}})
    return {"status": "success"}

@app.post("/api/update_instructions")
async def update_instructions(req: InstructionRequest, request: Request):
    user = await get_current_user(request)
    if user: await users_collection.update_one({"email": user['email']}, {"$set": {"custom_instruction": req.instruction[:1000]}})
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
    await chats_collection.insert_one({"session_id": new_id, "user_email": user['email'], "title": "New Chat", "messages": []})
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
    if user: await chats_collection.update_one({"session_id": req.session_id, "user_email": user['email']}, {"$set": {"title": req.new_title}})
    return {"status": "success"}

@app.delete("/api/delete_chat/{session_id}")
async def delete_chat_endpoint(session_id: str, request: Request):
    user = await get_current_user(request)
    if user: await chats_collection.delete_one({"session_id": session_id, "user_email": user['email']})
    return {"status": "success"}

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request):
    user = await get_current_user(request)
    if not user: return {"reply": "⚠️ Please Login first."}

    sid, mode, msg = req.session_id, req.mode, req.message
    
    image_object = None 
    vision_url = None   
    
    if req.file_data:
        try:
            if "," in req.file_data: header, encoded = req.file_data.split(",", 1)
            else: encoded = req.file_data
            file_bytes = base64.b64decode(encoded)
            file_type = req.file_type or ""

            if "pdf" in file_type:
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
                extracted_text = "\n\n[📄 PDF START]\n"
                for page in pdf_reader.pages:
                    text = page.extract_text()
                    if text: extracted_text += text + "\n"
                extracted_text += "[📄 PDF END]\n"
                msg += extracted_text
            
            elif "word" in file_type or "officedocument" in file_type:
                doc = Document(io.BytesIO(file_bytes))
                extracted_text = "\n\n[📄 DOC START]\n"
                for para in doc.paragraphs: extracted_text += para.text + "\n"
                extracted_text += "[📄 DOC END]\n"
                msg += extracted_text

            elif "image" in file_type:
                vision_url = req.file_data 
                image_object = PIL.Image.open(io.BytesIO(file_bytes)) 
                msg += " [🖼️ Image]"

        except Exception as e: return {"reply": f"⚠️ File Error: {str(e)}"}

    db_user = await users_collection.find_one({"email": user['email']})
    custom_instr = db_user.get("custom_instruction", "") if db_user else ""
    base_system = "You are Shanvika AI."
    if custom_instr: base_system += f"\n\nUSER INSTRUCTION:\n{custom_instr}\n\n"
    if mode == "coding": base_system += " You are an Expert Coder."

    chat = await chats_collection.find_one({"session_id": sid, "user_email": user['email']})
    if not chat:
        chat = {"session_id": sid, "user_email": user['email'], "title": "New Chat", "messages": []}
        await chats_collection.insert_one(chat)
    
    if len(chat["messages"]) == 0:
        title = msg[:30] if msg else "File Upload"
        await chats_collection.update_one({"session_id": sid}, {"$set": {"title": title}})

    await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "user", "content": msg}}})

    reply = ""
    try:
        if mode == "image_gen": reply = await generate_image_hf(msg)
        elif mode == "video": reply = await generate_video_hf(msg)
        elif mode == "coding":
            if image_object:
                model = genai.GenerativeModel('gemini-1.5-flash') 
                response = model.generate_content([msg, image_object])
                reply = response.text
            else: reply = await generate_gemini(msg, base_system)
        elif mode == "research":
            research_data = await asyncio.to_thread(perform_research, msg)
            client = get_groq()
            if research_data and client:
                completion = client.chat.completions.create(
                    messages=[{"role": "system", "content": base_system}, {"role": "user", "content": f"Data: {research_data}\nQuery: {msg}"}],
                    model="llama-3.3-70b-versatile"
                )
                reply = completion.choices[0].message.content
            else: reply = research_data or "⚠️ No results."
        else: # Default Chat
            client = get_groq()
            if client:
                if vision_url:
                    completion = client.chat.completions.create(
                        model="llama-3.2-90b-vision-preview", 
                        messages=[{"role": "user", "content": [{"type": "text", "text": msg}, {"type": "image_url", "image_url": {"url": vision_url}}]}]
                    )
                    reply = completion.choices[0].message.content
                else:
                    msgs = [{"role": "system", "content": base_system}]
                    msgs.extend(chat["messages"][-6:])
                    msgs.append({"role": "user", "content": msg}) 
                    completion = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=msgs)
                    reply = completion.choices[0].message.content
            else: reply = "⚠️ API Key missing."

    except Exception as e: reply = f"⚠️ Error: {str(e)}"

    await chats_collection.update_one({"session_id": sid}, {"$push": {"messages": {"role": "assistant", "content": reply}}})
    return {"reply": reply}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)