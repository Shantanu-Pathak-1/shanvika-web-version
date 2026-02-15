# ==================================================================================
#  FILE: tools_lab.py
#  DESCRIPTION: Backend Logic for All AI Tools (Fixed: Image Fallback & Singing)
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
import lyricsgenius # Added for Song Lyrics

# Load Keys
HF_TOKEN = os.getenv("HF_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GENIUS_API_KEY = os.getenv("GENIUS_API_KEY") # Add this in your environment

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
# [CATEGORY] 2. IMAGE GENERATION TOOL (FIXED: Gemini Prompt + Auto Fallback)
# ==================================================================================
async def generate_image_hf(prompt):
    # Step 1: Enhance Prompt using Gemini
    enhanced_prompt = prompt
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        enhancement_request = f"Convert this simple user idea into a highly detailed, professional AI image generation prompt (photorealistic, 8k, lighting details). User idea: '{prompt}'. Return ONLY the prompt text, no intro."
        res = model.generate_content(enhancement_request)
        if res.text:
            enhanced_prompt = res.text
    except:
        pass # Fallback to original if Gemini fails

    # Step 2: Try Hugging Face (FLUX)
    API_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    
    try:
        response = requests.post(API_URL, headers=headers, json={"inputs": enhanced_prompt}, timeout=25)
        
        if response.status_code == 200:
            image_bytes = response.content
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            return f"""
            <div class="glass p-2 rounded-xl">
                <p class="text-xs text-gray-400 mb-2">✨ Prompt: {enhanced_prompt[:100]}...</p>
                <img src="data:image/jpeg;base64,{base64_image}" alt="Generated Image" class="rounded-lg w-full">
            </div>
            """
        else:
            raise Exception("HF Busy")

    except Exception as e:
        # Step 3: FALLBACK to Pollinations AI (No Key Required, Very Stable)
        try:
            safe_prompt = enhanced_prompt.replace(" ", "%20")
            pollinations_url = f"https://image.pollinations.ai/prompt/{safe_prompt}"
            return f"""
            <div class="glass p-2 rounded-xl">
                <p class="text-xs text-yellow-400 mb-2">⚠️ Server Busy. Switched to Backup AI.</p>
                <img src="{pollinations_url}" alt="Generated Image" class="rounded-lg w-full">
            </div>
            """
        except:
            return "⚠️ All Image Servers are currently down. Please try again later."

# ==================================================================================
# [CATEGORY] 3. RESUME ANALYZER TOOL
# ==================================================================================
async def analyze_resume(file_data, user_msg):
    if not file_data:
        return "⚠️ Please upload a PDF resume first."
    
    try:
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
            header, encoded = file_data.split(",", 1)
            image_data = base64.b64decode(encoded)
            image = PIL.Image.open(io.BytesIO(image_data))
            response = model.generate_content(["Solve this math problem step-by-step:", image])
        else:
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
# [CATEGORY] 10. FUN MODE (FIXED: GENIUS API + GEMINI BACKUP)
# ==================================================================================
async def sing_with_me_tool(user_line, history):
    # Method 1: Try Genius API (Accurate Lyrics)
    if GENIUS_API_KEY:
        try:
            genius = lyricsgenius.Genius(GENIUS_API_KEY)
            # Search for the song based on user line
            song = genius.search_song(user_line)
            if song:
                lyrics = song.lyrics
                # Simple logic to find next line (Regex can be better but this is simple)
                lines = [l for l in lyrics.split('\n') if l.strip()]
                for i, line in enumerate(lines):
                    if user_line.lower() in line.lower() and i + 1 < len(lines):
                        return f"🎶 {lines[i+1]} 🎶\n(Song: {song.title} by {song.artist})"
        except:
            pass # Fallback to LLM if API fails or song not found

    # Method 2: Gemini / LLM Fallback (Creative Completion)
    prompt = f"""
    We are singing a duet. I am the female singer.
    User just sang: "{user_line}"
    
    Task: Identify the song (Bollywood/English) and sing the EXACT NEXT LINE.
    If you don't know the song, improvise a rhyming line romantically.
    Add musical emojis 🎶.
    """
    return get_llm_response(prompt)

# ==================================================================================
# [CATEGORY] 11. CURRENCY CONVERTER
# ==================================================================================
async def currency_tool(query):
    try:
        results = DDGS().text(f"convert {query}", max_results=1)
        if results:
            return f"💱 **Conversion:**\n{results[0]['body']}"
        else:
            return "⚠️ Could not fetch rates."
    except:
        return "⚠️ Currency service unavailable."
