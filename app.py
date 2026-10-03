import hashlib
import json
import re
import urllib.parse

import requests
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(page_title="Vishal AI", page_icon="🤖")


# ---------------- Secrets (Streamlit Cloud > Settings > Secrets) ----------------
def secret(name, default=""):
    try:
        return st.secrets[name]
    except Exception:
        return default


API_KEY = secret("GEMINI_API_KEY")
# Agar model name pe error aaye, aistudio.google.com pe dekho kaunsa Flash model available hai
MODEL = secret("GEMINI_MODEL", "gemini-2.5-flash")
ACCESS_CODE = secret("ACCESS_CODE")  # optional: sirf code wale log use kar sakein

if not API_KEY:
    st.error("GEMINI_API_KEY nahi mili. Streamlit Secrets me daalo.")
    st.stop()

if ACCESS_CODE and not st.session_state.get("ok"):
    code = st.text_input("Access code daalo", type="password")
    if code and code == ACCESS_CODE:
        st.session_state.ok = True
        st.rerun()
    st.stop()


@st.cache_resource
def get_client(key):
    return genai.Client(api_key=key)


client = get_client(API_KEY)

# ---------------- Personality + experts ----------------
BASE = """You are 'Vishal AI', a warm, smart AI companion and friend. Talk like a supportive friend, not a robot.
Reply in the user's language (Hinglish if they write Hinglish).
Understand what the user REALLY needs first. If unclear, ask ONE short question.
Give practical, step-by-step help with examples. Be honest, never invent facts,
correct mistakes kindly, and do not just agree with everything.
If a PDF or image is attached, analyse it carefully and answer from it. Say clearly if something is not in it.
Keep answers clear, not bloated."""

EXPERTS = {
    "engineer": "Role: senior software/electronics/mechanical engineer. Help with coding, debugging, projects, system design. Give working code with short comments.",
    "scientist": "Role: science and maths teacher. Explain from first principles with analogies, then exact formulas. Solve exam problems step by step and show common mistakes.",
    "manager": "Role: manager / boss mentor and career coach. Help with career, internships, resumes, interviews, leadership, productivity. Give clear action plans.",
    "finance": "Role: finance and trading EDUCATOR, not an advisor. Teach concepts and risk management. NEVER say buy/sell and never predict prices. Remind that markets are risky and to consult a SEBI-registered advisor.",
    "health": "Role: general health INFORMATION guide, not a doctor. No diagnosis, no medicine prescriptions. Tell the user to see a real doctor for symptoms. For emergencies or thoughts of self-harm, urge contacting emergency services or a trusted person immediately.",
    "astro": "Role: culture guide for astrology. Explain what traditions say, but state clearly that astrology has no scientific evidence and is for interest only. Never support big life, money or health decisions based on it.",
    "english": "Role: friendly English coach. Show the corrected sentence with a one-line reason, then give one small exercise. Praise progress.",
    "general": "Role: smart all-round helper for anything else.",
}

ROUTER_PROMPT = """Classify the user's message. Return JSON only: {{"mode": "<one of {modes}>", "image_prompt": "<string>"}}
mode meanings: engineer=coding/tech, scientist=physics/chem/maths/science, manager=career/internship/resume,
finance=money/trading/investing, health=body/fitness/sleep/symptoms, astro=astrology, english=practising English, general=else.
image_prompt: if the user asks to generate/draw/create an image, write a detailed English prompt for it. Otherwise "".
Never write image prompts for sexual, violent/gory, hateful content or real named people; use "" for those.
Message: {msg}"""


def route(text):
    try:
        r = client.models.generate_content(
            model=MODEL,
            contents=ROUTER_PROMPT.format(modes=list(EXPERTS), msg=text),
            config=types.GenerateContentConfig(
                temperature=0, response_mime_type="application/json"
            ),
        )
        d = json.loads(r.text)
        mode = d.get("mode", "general")
        return (mode if mode in EXPERTS else "general"), (d.get("image_prompt") or "").strip()
    except Exception:
        return "general", ""


def transcribe(audio_bytes):
    r = client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
            "Transcribe this speech exactly. Output only the transcript (keep Hinglish in Roman script).",
        ],
    )
    return (r.text or "").strip()


def gen_image(prompt):
    # Free image service (no key). Quality/availability can vary.
    url = (
        "https://image.pollinations.ai/prompt/"
        + urllib.parse.quote(prompt)
        + "?width=768&height=768&nologo=true"
    )
    try:
        r = requests.get(url, timeout=90)
        if r.ok and r.headers.get("content-type", "").startswith("image"):
            return r.content
    except Exception:
        pass
    return None


def speak_bytes(text, lang):
    from gtts import gTTS
    import io

    clean = re.sub(r"[*#`_>|-]", " ", text)[:700]
    buf = io.BytesIO()
    gTTS(clean, lang=lang).write_to_fp(buf)
    return buf.getvalue()


# ---------------- Sidebar ----------------
with st.sidebar:
    st.header("🤖 Vishal AI")
    pdf = st.file_uploader("📄 PDF analyse karwao", type=["pdf"])
    img = st.file_uploader("🖼️ Image dikhao", type=["png", "jpg", "jpeg", "webp"])
    audio = st.audio_input("🎙️ Bolke poocho") if hasattr(st, "audio_input") else None
    speak = st.toggle("🔊 Reply bolke sunao")
    voice_lang = st.selectbox("Awaaz ki bhasha", ["en", "hi"], index=0)
    if st.button("🧹 Nayi baatcheet"):
        st.session_state.messages = []
        st.rerun()
    st.caption("Tip: 'ek sunset ki image banao' bolke image bhi bana sakte ho.")

# ---------------- State + history ----------------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("last_audio", "")

st.title("Vishal AI 🤖")
st.caption("Engineer · Scientist · Manager · Finance · Health · English · PDF · Image · Voice")

if not st.session_state.messages:
    with st.chat_message("assistant"):
        st.markdown("Namaste! Main Vishal AI hoon. Kuch bhi poocho, PDF ya image bhejo, ya bolke baat karo 🙂")

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m.get("mode"):
            st.caption(f"{m['mode']} mode")
        st.markdown(m["content"])
        if m.get("image"):
            st.image(m["image"])


def build_contents():
    msgs = st.session_state.messages[-20:]
    while msgs and msgs[0]["role"] != "user":
        msgs = msgs[1:]
    contents = []
    for i, m in enumerate(msgs):
        parts = [types.Part(text=m["content"])]
        if m["role"] == "user" and i == len(msgs) - 1:
            if pdf:
                parts.insert(0, types.Part.from_bytes(data=pdf.getvalue(), mime_type="application/pdf"))
            if img:
                parts.insert(0, types.Part.from_bytes(data=img.getvalue(), mime_type=img.type or "image/png"))
        contents.append(
            types.Content(role="user" if m["role"] == "user" else "model", parts=parts)
        )
    return contents


# ---------------- Input ----------------
user_text = st.chat_input("Kuch bhi poocho...")

if audio is not None:
    data = audio.getvalue()
    h = hashlib.md5(data).hexdigest()
    if h != st.session_state.last_audio:
        st.session_state.last_audio = h
        try:
            with st.spinner("Sun raha hoon..."):
                spoken = transcribe(data)
            if spoken:
                user_text = spoken
        except Exception as e:
            st.warning(f"Awaaz samajh nahi aayi: {e}")

if user_text:
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    with st.chat_message("assistant"):
        try:
            mode, img_prompt = route(user_text)
            st.caption(f"{mode} mode")
            system = BASE + "\n" + EXPERTS[mode]
            if img_prompt:
                system += "\nAn image is being generated for the user right now. Reply briefly about what you are creating."
            with st.spinner("Soch raha hoon..."):
                r = client.models.generate_content(
                    model=MODEL,
                    contents=build_contents(),
                    config=types.GenerateContentConfig(system_instruction=system, temperature=0.7),
                )
            reply = r.text or "Sorry, jawab nahi aaya. Dobara try karo."
            st.markdown(reply)

            image_bytes = None
            if img_prompt:
                with st.spinner("Image ban rahi hai..."):
                    image_bytes = gen_image(img_prompt)
                if image_bytes:
                    st.image(image_bytes)
                else:
                    st.warning("Image abhi nahi ban payi. Thodi der baad try karo.")

            if speak:
                try:
                    st.audio(speak_bytes(reply, voice_lang), format="audio/mp3")
                except Exception:
                    st.caption("(Awaaz abhi nahi ban payi)")

            st.session_state.messages.append(
                {"role": "assistant", "content": reply, "mode": mode, "image": image_bytes}
            )
        except Exception as e:
            st.session_state.messages.pop()  # failed turn hata do
            st.error("Kuch gadbad ho gayi (free limit ya model name ho sakta hai). Thodi der baad try karo.")
            st.caption(str(e)[:300])
