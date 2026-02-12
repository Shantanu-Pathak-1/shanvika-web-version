import os
import random
import base64
import io
import httpx
import qrcode
import PyPDF2
import secrets 
import string
import sympy 
import google.generativeai as genai
from duckduckgo_search import DDGS
from youtube_transcript_api import YouTubeTranscriptApi

# --- Helper: Key Rotation ---
def get_tool_gemini_key():
    keys_str = os.getenv("GEMINI_API_KEY_POOL", "")
    if not keys_str: return os.getenv("GEMINI_API_KEY")
    keys_list = [k.strip() for k in keys_str.split(",") if k.strip()]
    return random.choice(keys_list) if keys_list else None

# ==========================================
# 🎤 BATCH 6: ENTERTAINMENT (NEW)
# ==========================================

# tools_lab.py mein 'sing_with_me_tool' ko isse replace karo:

async def sing_with_me_tool(user_lyric, context_history=""):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # 👇 IMPROVED PROMPT WITH CONTEXT
        sys_prompt = (
            "You are an expert Bollywood & English singer partner. "
            "Your Goal: Maintain the flow of the song perfectly."
            "CONTEXT RULES:"
            f"1. Previous lines sung in this session: '{context_history}' (Use this to know which song is playing)."
            "2. Identify the song based on User's current line AND context."
            "3. If the user continues the song correctly, you sing the NEXT line."
            "4. If the user switches the song, start the new song."
            "5. Output ONLY the lyrics + romantic emojis. No explanations."
        )
        
        response = model.generate_content(f"{sys_prompt}\n\nUser just sang: '{user_lyric}'\nYour next line:")
        
        return f"""
        <div class="glass p-4 rounded-xl border border-pink-500/40 text-center relative overflow-hidden">
            <div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-pink-500 to-transparent opacity-50"></div>
            <div class="mb-2 animate-bounce inline-block"><span class="text-2xl">🎤</span><span class="text-xl">🎶</span></div>
            <h3 class="text-lg font-serif text-pink-300 italic leading-relaxed">"{response.text.strip()}"</h3>
            <p class="text-[10px] text-gray-500 mt-3">Next line tum gao... 😉</p>
        </div>
        """
    except Exception as e: return f"⚠️ Singing Error: {str(e)}"

# ==========================================
# 🧠 BATCH 5: SMART UTILITIES
# ==========================================

async def solve_math_problem(file_data, user_query):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        vision_input = None
        if file_data:
            if "," in file_data: _, encoded = file_data.split(",", 1)
            else: encoded = file_data
            vision_input = {'mime_type': 'image/jpeg', 'data': base64.b64decode(encoded)}
        
        prompt = f"Solve step-by-step. 1. Concept 2. Stepwise Calc 3. Final Answer. Q: {user_query}"
        content = [prompt, vision_input] if vision_input else prompt
        response = model.generate_content(content)
        return f"""<div class="glass p-4 rounded-xl border border-indigo-500/30"><h3 class="text-lg font-bold text-indigo-400 mb-2"><i class="fas fa-calculator"></i> Math Solution</h3><div class="text-sm text-gray-200 space-y-2 whitespace-pre-wrap leading-relaxed">{response.text}</div></div>"""
    except Exception as e: return f"⚠️ Math Error: {str(e)}"

async def smart_todo_maker(raw_text):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Convert to HTML Table with columns: Task, Priority (High/Med/Low), Deadline. Input: '{raw_text}'"
        response = model.generate_content(prompt)
        return f"""<div class="glass p-4 rounded-xl border border-teal-500/30"><h3 class="text-lg font-bold text-teal-400 mb-3"><i class="fas fa-tasks"></i> Smart Task List</h3><div class="overflow-x-auto">{response.text}</div></div>"""
    except Exception as e: return f"⚠️ Error: {str(e)}"

async def build_pro_resume(user_data):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Create Harvard-Standard Resume (HTML/Markdown). Structure: Header, Summary, Experience, Skills. Data: '{user_data}'"
        response = model.generate_content(prompt)
        return f"""<div class="glass p-5 rounded-xl border border-slate-500/30"><div class="flex justify-between items-center mb-4"><h3 class="text-lg font-bold text-slate-300"><i class="fas fa-file-contract"></i> Generated Resume</h3><button onclick="navigator.clipboard.writeText(this.parentElement.nextElementSibling.innerText); alert('Copied!')" class="text-xs bg-slate-700 px-2 py-1 rounded hover:bg-slate-600">Copy Text</button></div><div class="bg-white text-black p-6 rounded-lg text-sm font-serif leading-relaxed shadow-lg select-all">{response.text}</div></div>"""
    except Exception as e: return f"⚠️ Error: {str(e)}"

# ==========================================
# 🎓 BATCH 4: INTERVIEW
# ==========================================

async def generate_interview_questions(role_topic):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(f"Generate 10 interview questions for: '{role_topic}'. HTML bullet points.")
        return f"""<div class="glass p-4 rounded-xl border border-orange-500/30"><h3 class="text-lg font-bold text-orange-400 mb-3"><i class="fas fa-list-ul"></i> Top Questions</h3><div class="text-sm text-gray-200 space-y-2">{response.text}</div></div>"""
    except: return "⚠️ Error"

async def handle_mock_interview(user_msg):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        sys = "You are technical interviewer Shanvika. If Role given -> Ask Q1. If Answer given -> Rate & Ask Next."
        response = model.generate_content(f"{sys}\nUser: {user_msg}")
        return f"""<div class="glass p-4 rounded-xl border border-cyan-500/30"><div class="flex items-center gap-2 mb-2"><div class="w-8 h-8 rounded-full bg-cyan-500/20 flex items-center justify-center"><i class="fas fa-user-tie text-cyan-400"></i></div><h3 class="font-bold text-cyan-400">Mock Interviewer</h3></div><div class="text-sm text-gray-200 leading-relaxed">{response.text}</div><div class="mt-3 text-[10px] text-gray-500 border-t border-white/10 pt-2">Type answer below...</div></div>"""
    except: return "⚠️ Error"

# ==========================================
# 📺 BATCH 3: STUDENT SAVERS
# ==========================================

async def summarize_youtube(video_url):
    try:
        if "v=" in video_url: vid = video_url.split("v=")[1].split("&")[0]
        else: vid = video_url.split("/")[-1]
        transcript = YouTubeTranscriptApi.get_transcript(vid)
        full_text = " ".join([t['text'] for t in transcript])
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(f"Summarize video transcript in bullet points. Text: {full_text[:10000]}")
        return f"""<div class="glass p-4 rounded-xl border border-red-500/30"><h3 class="text-lg font-bold text-red-400 mb-2"><i class="fab fa-youtube"></i> Video Summary</h3><div class="text-sm text-gray-200 space-y-2 leading-relaxed">{response.text}</div></div>"""
    except: return "⚠️ Video must have captions enabled."

async def generate_password_tool(inp):
    try:
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        pwd = ''.join(secrets.choice(chars) for _ in range(12))
        return f"""<div class="glass p-4 rounded-xl border border-green-500/30 text-center"><h3 class="text-sm font-bold text-green-400 mb-2">🔐 Secure Password</h3><div class="bg-black/50 p-3 rounded-lg text-white font-mono text-xl tracking-widest mb-3 select-all border border-gray-600">{pwd}</div></div>"""
    except: return "⚠️ Error"

async def fix_grammar_tool(text):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(f"Fix grammar & spelling. Output ONLY corrected text.\nInput: '{text}'")
        return f"""<div class="glass p-4 rounded-xl border border-yellow-500/30"><h3 class="text-sm font-bold text-yellow-400 mb-2">✨ Polished Text:</h3><div class="bg-white/10 p-3 rounded-lg text-white text-sm italic select-all">{response.text.strip()}</div></div>"""
    except: return "⚠️ Error"

# ==========================================
# 🛠️ BATCH 1 & 2: ESSENTIALS
# ==========================================

async def analyze_resume(file_data, q):
    try:
        if not file_data: return "⚠️ Upload PDF."
        decoded = base64.b64decode(file_data.split(",")[1] if "," in file_data else file_data)
        reader = PyPDF2.PdfReader(io.BytesIO(decoded))
        text = "\n".join([p.extract_text() for p in reader.pages])
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(f"Review Resume. Score/100, Strengths, Weaknesses. Text: {text[:4000]}")
        return f"""<div class="glass p-4 rounded-xl border border-blue-500/30"><h3 class="text-lg font-bold text-blue-400 mb-3"><i class="fas fa-file-invoice"></i> Resume Scorecard</h3><div class="text-sm text-gray-200 space-y-2 whitespace-pre-wrap">{response.text}</div></div>"""
    except Exception as e: return f"⚠️ Error: {str(e)}"

async def review_github(url):
    try:
        user = url.split('/')[-1].strip()
        async with httpx.AsyncClient() as client:
            data = (await client.get(f"https://api.github.com/users/{user}")).json()
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(f"Review GitHub Profile: {user}, Bio: {data.get('bio','N/A')}, Repos: {data.get('public_repos',0)}. Rate /10.")
        return f"""<div class="glass p-4 rounded-xl border border-gray-600"><div class="flex items-center gap-3 mb-3"><img src="{data.get('avatar_url','')}" class="w-12 h-12 rounded-full"><div><h3 class="font-bold text-white">{data.get('name',user)}</h3><p class="text-xs text-gray-400">@{user}</p></div></div><div class="text-sm text-gray-300 mt-2">{response.text}</div></div>"""
    except: return "⚠️ Error or User Not Found."

async def currency_tool(q):
    try:
        res = DDGS().text(f"exchange rate {q}", max_results=1)[0]['body']
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(f"Convert: '{q}'. Based on: '{res}', format: '10 USD = 830 INR'. Short.")
        return f"""<div class="glass p-3 rounded-xl border border-green-500/30 text-center"><h3 class="text-xl font-bold text-green-400"><i class="fas fa-coins"></i> Conversion</h3><p class="text-lg text-white mt-2 font-mono">{response.text.strip()}</p></div>"""
    except: return "⚠️ Error"

async def generate_prompt_only(text):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(f"Write detailed art prompt for: '{text}'. Output text only.")
        return f"""<div class="glass p-4 rounded-xl border border-pink-500/30"><h3 class="text-sm font-bold text-pink-400 mb-2">✨ Prompt:</h3><div class="bg-black/40 p-3 rounded-lg text-gray-300 text-sm italic mb-3 select-all">{response.text.strip()}</div></div>"""
    except: return "⚠️ Error"

async def generate_qr_code(data):
    try:
        img = qrcode.make(data); buf = io.BytesIO(); img.save(buf, format="PNG"); 
        b64 = base64.b64encode(buf.getvalue()).decode()
        return f"""<div class="glass p-4 rounded-xl text-center"><img src="data:image/png;base64,{b64}" class="mx-auto rounded-lg w-48"><a href="data:image/png;base64,{b64}" download="qr.png" class="inline-block mt-2 bg-white text-black px-4 py-1 rounded text-xs font-bold">Download</a></div>"""
    except: return "⚠️ Error"

async def generate_image_hf(prompt):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        p = model.generate_content(f"Refine art prompt (max 20 words): {prompt}").text.replace(" ","%20")
        url = f"https://image.pollinations.ai/prompt/{p}?width=1024&height=1024&nologo=true"
        return f"""<div class="glass p-2 rounded-lg mt-2"><img src='{url}' class='rounded-lg shadow-lg w-full'><a href="{url}" target="_blank" class="block text-center text-pink-500 text-xs mt-2 hover:underline">Download</a></div>"""
    except: return "⚠️ Error"