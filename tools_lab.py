import os
import random
import base64
import io
import httpx
import qrcode
import PyPDF2
import secrets 
import string
import google.generativeai as genai
from duckduckgo_search import DDGS
from youtube_transcript_api import YouTubeTranscriptApi

# --- Helper: Key Rotation for Tools ---
def get_tool_gemini_key():
    keys_str = os.getenv("GEMINI_API_KEY_POOL", "")
    if not keys_str: return os.getenv("GEMINI_API_KEY")
    keys_list = [k.strip() for k in keys_str.split(",") if k.strip()]
    return random.choice(keys_list) if keys_list else None

# ==========================================
# 🎨 BATCH 1: CREATIVE TOOLS
# ==========================================

async def generate_prompt_only(user_text):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Act as a professional Midjourney/Flux Prompt Engineer. Write a highly detailed prompt based on: '{user_text}'. Output ONLY the prompt text."
        response = model.generate_content(prompt)
        return f"""<div class="glass p-4 rounded-xl border border-pink-500/30"><h3 class="text-sm font-bold text-pink-400 mb-2">✨ Professional Prompt:</h3><div class="bg-black/40 p-3 rounded-lg text-gray-300 text-sm italic mb-3 select-all">{response.text.strip()}</div><p class="text-[10px] text-gray-500">Copy this for Image Gen.</p></div>"""
    except Exception as e: return f"⚠️ Error: {str(e)}"

async def generate_qr_code(data):
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"""<div class="glass p-4 rounded-xl text-center"><h3 class="text-sm font-bold text-white mb-2">📱 Your QR Code</h3><img src="data:image/png;base64,{img_str}" class="mx-auto rounded-lg shadow-lg w-48 h-48"><a href="data:image/png;base64,{img_str}" download="qr.png" class="inline-block mt-2 bg-white text-black px-4 py-1 rounded text-xs font-bold">Download PNG</a></div>"""
    except Exception as e: return f"⚠️ QR Error: {str(e)}"

async def generate_image_hf(user_prompt):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        enhancement = model.generate_content(f"Refine art prompt (under 30 words): {user_prompt}").text
        seed = random.randint(1, 1000000)
        safe_prompt = enhancement.replace(" ", "%20")
        image_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1024&height=1024&seed={seed}&model=flux&nologo=true"
        return f"""<div class="glass p-2 rounded-lg mt-2"><img src='{image_url}' class='rounded-lg shadow-lg w-full'><a href="{image_url}" target="_blank" class="block text-center text-pink-500 text-xs mt-2 hover:underline">Download HD</a></div>"""
    except: return "⚠️ Image Gen Failed."

# ==========================================
# 🛠️ BATCH 2: UTILITY TOOLS
# ==========================================

async def analyze_resume(file_data, user_query):
    try:
        if not file_data: return "⚠️ Please upload a Resume (PDF) first."
        if "," in file_data: header, encoded = file_data.split(",", 1)
        else: encoded = file_data
        decoded = base64.b64decode(encoded)
        reader = PyPDF2.PdfReader(io.BytesIO(decoded))
        resume_text = "\n".join([p.extract_text() for p in reader.pages])
        
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Act as a Senior HR. Review this resume. Give Score /100, 3 Strengths, 3 Weaknesses, and Advice. Resume: {resume_text[:4000]}"
        response = model.generate_content(prompt)
        return f"""<div class="glass p-4 rounded-xl border border-blue-500/30"><h3 class="text-lg font-bold text-blue-400 mb-3"><i class="fas fa-file-invoice"></i> Resume Scorecard</h3><div class="text-sm text-gray-200 space-y-2 whitespace-pre-wrap">{response.text}</div></div>"""
    except Exception as e: return f"⚠️ Resume Error: {str(e)}"

async def review_github(username_url):
    try:
        username = username_url.split('/')[-1].strip()
        async with httpx.AsyncClient() as client:
            res = await client.get(f"https://api.github.com/users/{username}")
            if res.status_code != 200: return "⚠️ GitHub User Not Found."
            data = res.json()
            repos = (await client.get(data['repos_url'])).json()[:5]
        repo_names = ", ".join([r['name'] for r in repos])
        
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Review GitHub: {username}, Bio: {data.get('bio','None')}, Repos: {data['public_repos']}, Projects: {repo_names}. Rate /10."
        response = model.generate_content(prompt)
        return f"""<div class="glass p-4 rounded-xl border border-gray-600"><div class="flex items-center gap-3 mb-3"><img src="{data['avatar_url']}" class="w-12 h-12 rounded-full border border-white/20"><div><h3 class="font-bold text-white">{data['name'] or username}</h3><p class="text-xs text-gray-400">@{username}</p></div></div><div class="text-sm text-gray-300 mt-2 whitespace-pre-wrap">{response.text}</div></div>"""
    except Exception as e: return f"⚠️ GitHub Error: {str(e)}"

async def currency_tool(query):
    try:
        search_q = f"exchange rate {query}"
        results = DDGS().text(search_q, max_results=1)
        snippet = results[0]['body'] if results else "Rate not found"
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Convert: '{query}'. Based on data: '{snippet}', output format: '10 USD = 830 INR'. Short answer."
        response = model.generate_content(prompt)
        return f"""<div class="glass p-3 rounded-xl border border-green-500/30 text-center"><h3 class="text-xl font-bold text-green-400"><i class="fas fa-coins"></i> Conversion</h3><p class="text-lg text-white mt-2 font-mono">{response.text.strip()}</p></div>"""
    except Exception as e: return f"⚠️ Error: {str(e)}"

# ==========================================
# 📺 BATCH 3: STUDENT SAVERS
# ==========================================

async def summarize_youtube(video_url):
    try:
        if "v=" in video_url: vid = video_url.split("v=")[1].split("&")[0]
        else: vid = video_url.split("/")[-1]
        try:
            transcript = YouTubeTranscriptApi.get_transcript(vid)
            full_text = " ".join([t['text'] for t in transcript])
        except: return "⚠️ Ensure video has captions enabled."
        
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Summarize video transcript in bullet points. Key lessons & takeaways. Text: {full_text[:10000]}"
        response = model.generate_content(prompt)
        return f"""<div class="glass p-4 rounded-xl border border-red-500/30"><h3 class="text-lg font-bold text-red-400 mb-2"><i class="fab fa-youtube"></i> Video Summary</h3><div class="text-sm text-gray-200 space-y-2 leading-relaxed">{response.text}</div></div>"""
    except Exception as e: return f"⚠️ Error: {str(e)}"

async def generate_password_tool(user_input):
    try:
        length = 12
        import re
        nums = re.findall(r'\d+', user_input)
        if nums: length = min(int(nums[0]), 50)
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()_+"
        password = ''.join(secrets.choice(alphabet) for i in range(length))
        return f"""<div class="glass p-4 rounded-xl border border-green-500/30 text-center"><h3 class="text-sm font-bold text-green-400 mb-2">🔐 Secure Password</h3><div class="bg-black/50 p-3 rounded-lg text-white font-mono text-xl tracking-widest mb-3 select-all border border-gray-600">{password}</div></div>"""
    except: return "⚠️ Error"

async def fix_grammar_tool(text):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Fix grammar, spelling, and punctuation. Output ONLY corrected text.\n\nInput: '{text}'"
        response = model.generate_content(prompt)
        return f"""<div class="glass p-4 rounded-xl border border-yellow-500/30"><h3 class="text-sm font-bold text-yellow-400 mb-2">✨ Polished Text:</h3><div class="bg-white/10 p-3 rounded-lg text-white text-sm italic select-all">{response.text.strip()}</div></div>"""
    except: return "⚠️ Error"

# ==========================================
# 🎓 BATCH 4: INTERVIEW TOOLS
# ==========================================

async def generate_interview_questions(role_topic):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        prompt = f"Generate 10 interview questions for role: '{role_topic}'. Mix of basic & tricky. Format as HTML bullet points."
        response = model.generate_content(prompt)
        return f"""<div class="glass p-4 rounded-xl border border-orange-500/30"><h3 class="text-lg font-bold text-orange-400 mb-3"><i class="fas fa-list-ul"></i> Top Questions</h3><div class="text-sm text-gray-200 space-y-2">{response.text}</div></div>"""
    except: return "⚠️ Error"

async def handle_mock_interview(user_msg):
    try:
        api_key = get_tool_gemini_key()
        if api_key: genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        sys_prompt = "You are a strict technical interviewer named Shanvika. 1. If user gives a Role, START interview with 1st question. 2. If user gives Answer, Rate /10 and ASK NEXT QUESTION. 3. Ask ONE question at a time."
        response = model.generate_content(f"{sys_prompt}\n\nUser Input: {user_msg}")
        return f"""<div class="glass p-4 rounded-xl border border-cyan-500/30"><div class="flex items-center gap-2 mb-2"><div class="w-8 h-8 rounded-full bg-cyan-500/20 flex items-center justify-center"><i class="fas fa-user-tie text-cyan-400"></i></div><h3 class="font-bold text-cyan-400">Mock Interviewer</h3></div><div class="text-sm text-gray-200 leading-relaxed">{response.text}</div><div class="mt-3 text-[10px] text-gray-500 border-t border-white/10 pt-2">Type answer below...</div></div>"""
    except: return "⚠️ Error"