"""
শিখি ব্যাকএন্ড — FastAPI অ্যাপ।

এন্ডপয়েন্ট:
  POST /videos   -> নতুন ভিডিও লিংক জমা দেওয়া, ব্যাকগ্রাউন্ডে প্রসেসিং শুরু হয়
  GET  /videos   -> সব ভিডিওর লিস্ট + স্ট্যাটাস
  POST /chat     -> প্রশ্ন করলে RAG দিয়ে উত্তর ফেরত আসে
  POST /whatsapp -> Meta/Twilio WhatsApp webhook (নিচে টুকরো করে ব্যাখ্যা করা আছে)

লোকালি রান করতে:
  pip install -r requirements.txt
  export GROQ_API_KEY=gsk_...
  uvicorn main:app --reload
"""
import os
import traceback
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

import database
import transcribe
import rag

load_dotenv()

app = FastAPI(title="শিখি ব্যাকএন্ড")

# ডেমো/MVP-র জন্য সব origin থেকে রিকোয়েস্ট allow করা হয়েছে।
# প্রোডাকশনে গেলে নিজের ফ্রন্টএন্ড ডোমেইন দিয়ে সীমাবদ্ধ করে দিন।
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

database.init_db()


class VideoIn(BaseModel):
    link: str
    professional: str
    topic: str


class ChatIn(BaseModel):
    question: str


def _process_video(video_id: str, link: str):
    try:
        transcript = transcribe.transcribe_video(link)
        if not transcript:
            database.update_video_status(video_id, "failed", error="ট্রান্সক্রিপ্ট খালি এসেছে")
            return
        database.update_video_status(video_id, "transcribed", transcript=transcript)
        rag.process_and_store_transcript(video_id, transcript)
        database.update_video_status(video_id, "ready")
    except Exception as e:  # noqa: BLE001
        print(f"[VIDEO PROCESSING FAILED] video_id={video_id} link={link}")
        print(traceback.format_exc())  # এটা এখন সরাসরি Railway Deploy Logs-এ দেখা যাবে
        database.update_video_status(video_id, "failed", error=str(e))


@app.post("/videos")
def add_video(payload: VideoIn, background_tasks: BackgroundTasks):
    video = database.create_video(payload.link, payload.professional, payload.topic)
    background_tasks.add_task(_process_video, video["id"], payload.link)
    return video


@app.get("/videos")
def get_videos():
    return database.list_videos()


@app.get("/videos/{video_id}")
def get_video_detail(video_id: str):
    video = database.get_video(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="ভিডিও পাওয়া যায়নি।")
    return video


@app.post("/chat")
def chat(payload: ChatIn):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="প্রশ্ন খালি হতে পারবে না।")
    return rag.generate_answer(payload.question)


@app.get("/")
def health():
    return {"status": "ok", "service": "shikhi-backend"}


# ---------------------------------------------------------------------------
# WhatsApp webhook (Meta Cloud API উদাহরণ)।
# এটা কাজ করানোর জন্য আপনাকে আলাদাভাবে করতে হবে:
#   1. Meta for Developers-এ WhatsApp Business অ্যাপ বানানো
#   2. এই URL-টা (https://your-backend/whatsapp) ওদের webhook হিসেবে দেওয়া
#   3. WHATSAPP_VERIFY_TOKEN আর WHATSAPP_ACCESS_TOKEN env var সেট করা
# ---------------------------------------------------------------------------
import httpx  # noqa: E402

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")


from fastapi import Request  # noqa: E402
from fastapi.responses import PlainTextResponse  # noqa: E402


@app.get("/whatsapp")
def verify_webhook(request: Request):
    # Meta ভেরিফিকেশন হ্যান্ডশেক
    params = request.query_params
    if params.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(params.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="ভেরিফিকেশন টোকেন মিলছে না।")


@app.post("/whatsapp")
async def whatsapp_webhook(payload: dict):
    try:
        entry = payload["entry"][0]["changes"][0]["value"]
        message = entry["messages"][0]
        from_number = message["from"]
        text = message["text"]["body"]
    except (KeyError, IndexError):
        return {"status": "ignored"}

    result = rag.generate_answer(text)
    reply_text = result["answer"]
    if result["sources"]:
        src_line = ", ".join(f"{s['professional']} ({s['topic']})" for s in result["sources"])
        reply_text += f"\n\nসূত্র: {src_line}"

    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://graph.facebook.com/v20.0/{WHATSAPP_PHONE_NUMBER_ID}/messages",
            headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"},
            json={
                "messaging_product": "whatsapp",
                "to": from_number,
                "text": {"body": reply_text},
            },
        )
    return {"status": "sent"}
