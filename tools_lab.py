# ==================================================================================
#  FILE: tools_lab.py
#  DESCRIPTION: Backend Logic for All AI Tools (Image, Resume, YouTube, etc.)
#  CATEGORIES:
#    1. IMPORTS & API SETUP
#    2. IMAGE GENERATION TOOL
#    3. RESUME ANALYZER TOOL
#    4. GITHUB PROFILE REVIEWER
#    5. YOUTUBE VIDEO SUMMARIZER
#    6. INTERVIEW PREP TOOLS (Mock & Questions)
#    7. MATH SOLVER (Vision API)
#    8. PRODUCTIVITY TOOLS (Todo, Password, QR)
#    9. WRITING ASSISTANTS (Grammar, Prompt, Resume Builder)
#    10. FUN MODE (Sing With Me)
#    11. CURRENCY CONVERTER
# ==================================================================================

# [CATEGORY] 1. IMPORTS & API SETUP
import os
import random
import string
import requests
import qrcode
import io
import base64
import PyPDF2
from youtube_transcript_api import YouTubeTranscriptApi
from duckduckgo_search import DDGS
import google.generativeai as genai
from groq import Groq
import PIL.Image

# Load Keys
HF_TOKEN = os.getenv("HF_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configure GenAI
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Helper for LLM Calls
def get_llm_response(prompt, model="llama-3.3-70b-versatile"):
    try:
        client = Groq(api_key=GROQ_API_KEY)
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=model,
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"⚠️ LLM Error: {str(e)}"

# ==================================================================================
# [CATEGORY] 2. IMAGE GENERATION TOOL
# ==================================================================================
async def generate_image_hf(prompt):
    API_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    
    try:
        # Enhance prompt for better results
        enhanced_prompt = f"High quality, 8k, realistic, detailed: {prompt}"
        response = requests.post(API_URL, headers=headers, json={"inputs": enhanced_prompt})
        
        if response.status_code == 200:
            image_bytes = response.content
            # Convert to Base64 to send to frontend
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            return f'<div class="glass p-2 rounded-xl"><img src="data:image/jpeg;base64,{base64_image}" alt="Generated Image" class="rounded-lg w-full"></div>'
        else:
            return "⚠️ Image Generation Failed. Server Busy."
    except Exception as e:
        return f"Error: {str(e)}"

# ==================================================================================
# [CATEGORY] 3. RESUME ANALYZER TOOL
# ==================================================================================
async def analyze_resume(file_data, user_msg):
    if not file_data:
        return "⚠️ Please upload a PDF resume first."
    
    try:
        # Decode Base64 PDF
        header, encoded = file_data.split(",", 1)
        pdf_bytes = base64.b64decode(encoded)
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text()
            
        prompt = f"""
        Act as an expert HR Manager. Analyze this resume:
        {text[:3000]}... (truncated)
        
        Provide:
        1. A Score out of 100.
        2. Top 3 Strengths.
        3. Top 3 Weaknesses.
        4. Specific improvements for better ATS ranking.
        """
        return get_llm_response(prompt)
    except Exception as e:
        return f"⚠️ Could not read PDF. Ensure it's a valid file. Error: {str(e)}"

# ==================================================================================
# [CATEGORY] 4. GITHUB PROFILE REVIEWER
# ==================================================================================
async def review_github(url):
    username = url.split("/")[-1]
    if not username: return "⚠️ Invalid GitHub URL."
    
    try:
        # Fetch Public Data
        api_url = f"https://api.github.com/users/{username}"
        repos_url = f"https://api.github.com/users/{username}/repos?sort=updated"
        
        user_data = requests.get(api_url).json()
        repos_data = requests.get(repos_url).json()
        
        if "message" in user_data: return "⚠️ User not found."
        
        bio = user_data.get('bio', 'No bio')
        public_repos = user_data.get('public_repos', 0)
        followers = user_data.get('followers', 0)
        
        top_repos = [r['name'] for r in repos_data[:5]]
        
        prompt = f"""
        Review this GitHub Profile:
        User: {username}
        Bio: {bio}
        Repos: {public_repos}
        Followers: {followers}
        Recent Projects: {', '.join(top_repos)}
        
        Give a professional rating (Junior/Mid/Senior), point out what's missing (e.g., Readme, Activity), and suggest project ideas to improve.
        """
        return get_llm_response(prompt)
    except Exception as e:
        return f"⚠️ Error fetching GitHub data: {str(e)}"

# ==================================================================================
# [CATEGORY] 5. YOUTUBE VIDEO SUMMARIZER
# ==================================================================================
async def summarize_youtube(url):
    try:
        video_id = url.split("v=")[1].split("&")[0]
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        full_text = " ".join([i['text'] for i in transcript_list])
        
        prompt = f"""
        Summarize this YouTube video transcript into 5 key bullet points with timestamps if possible.
        Text: {full_text[:4000]}...
        """
        return get_llm_response(prompt)
    except:
        return "⚠️ Could not fetch transcript. Video might not have captions enabled."

# ==================================================================================
# [CATEGORY] 6. INTERVIEW PREP TOOLS
# ==================================================================================
async def generate_interview_questions(role):
    prompt = f"Generate 10 hard technical and behavioral interview questions for a {role} position. Format them nicely."
    return get_llm_response(prompt)

async def handle_mock_interview(msg):
    # This is a conversational tool, so it relies on chat history in main.py usually.
    # Here we just generate the interviewer persona response.
    prompt = f"You are a strict interviewer. The user said: '{msg}'. Reply professionally, ask a follow-up question, or evaluate their answer."
    return get_llm_response(prompt)

# ==================================================================================
# [CATEGORY] 7. MATH SOLVER
# ==================================================================================
async def solve_math_problem(file_data, query):
    if not file_data and not query: return "⚠️ Please provide an image or a math problem."
    
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        if file_data:
            # Image based solving
            header, encoded = file_data.split(",", 1)
            image_data = base64.b64decode(encoded)
            image = PIL.Image.open(io.BytesIO(image_data))
            response = model.generate_content(["Solve this math problem step-by-step:", image])
        else:
            # Text based solving
            response = model.generate_content(f"Solve this math problem step-by-step: {query}")
            
        return response.text
    except Exception as e:
        return f"⚠️ Math Solver Error: {str(e)}"

# ==================================================================================
# [CATEGORY] 8. PRODUCTIVITY TOOLS
# ==================================================================================
async def smart_todo_maker(raw_text):
    prompt = f"""
    Convert this rough text into a structured To-Do List with priority levels (High/Medium/Low) and estimated time.
    Raw Text: {raw_text}
    """
    return get_llm_response(prompt)

async def generate_password_tool(req):
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(random.choice(chars) for i in range(12))
    return f"🔐 **Generated Password:** `{password}`\n\n(Click to copy)"

async def generate_qr_code(text):
    qr = qrcode.make(text)
    buffered = io.BytesIO()
    qr.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    return f'<div class="flex justify-center p-4 bg-white rounded-xl w-fit mx-auto"><img src="data:image/png;base64,{img_str}" alt="QR Code" width="200"></div>'

# ==================================================================================
# [CATEGORY] 9. WRITING ASSISTANTS
# ==================================================================================
async def fix_grammar_tool(text):
    prompt = f"Fix the grammar, spelling, and punctuation of this text. Make it professional:\n\n{text}"
    return get_llm_response(prompt)

async def generate_prompt_only(idea):
    prompt = f"Write a highly detailed, professional AI image generation prompt for Midjourney/Flux based on this idea: '{idea}'. Include lighting, style, and camera settings."
    return get_llm_response(prompt)

async def build_pro_resume(details):
    prompt = f"Create a professional Resume structure (Markdown) for a candidate with these details: {details}"
    return get_llm_response(prompt)

# ==================================================================================
# [CATEGORY] 10. FUN MODE
# ==================================================================================
async def sing_with_me_tool(user_line, history):
    prompt = f"""
    We are singing a duet. I am the female singer.
    Context so far: {history}
    User just sang: "{user_line}"
    
    Complete the lyrics or sing the next line of the song. 
    Add musical emojis 🎶. Keep it romantic and fun.
    If you don't know the song, politely ask to start a popular one.
    """
    return get_llm_response(prompt)

# ==================================================================================
# [CATEGORY] 11. CURRENCY CONVERTER
# ==================================================================================
async def currency_tool(query):
    # Using DuckDuckGo for quick conversion results as it's free and real-time
    try:
        results = DDGS().text(f"convert {query}", max_results=1)
        if results:
            return f"💱 **Conversion:**\n{results[0]['body']}"
        else:
            return "⚠️ Could not fetch rates."
    except:
        return "⚠️ Currency service unavailable."