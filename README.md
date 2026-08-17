# শিখি — ব্যাকএন্ড (MVP)

এটা আপনার `index.html` ফ্রন্টএন্ডের সাথে কানেক্ট হওয়ার জন্য বানানো ব্যাকএন্ড। এতে আছে:

- **POST /videos** — ভিডিও লিংক জমা দিলে ব্যাকগ্রাউন্ডে অডিও ডাউনলোড (yt-dlp) + ট্রান্সক্রিপ্ট (faster-whisper) + এমবেডিং তৈরি করে SQLite-এ সেভ করে।
- **GET /videos** — সব ভিডিওর স্ট্যাটাস (`processing` → `transcribed` → `ready`, বা `failed`)।
- **POST /chat** — প্রশ্ন নিয়ে RAG দিয়ে (relevant chunk খুঁজে + Claude API দিয়ে) উত্তর জেনারেট করে, উৎসসহ।
- **GET/POST /whatsapp** — Meta WhatsApp Cloud API webhook (অপশনাল, Phase 4)।

## ১. লোকালি টেস্ট করা

```bash
cd shikhi-backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env ফাইলে GROQ_API_KEY বসান (console.groq.com/keys থেকে ফ্রি নেওয়া যায়)

uvicorn main:app --reload
```

তারপর `http://127.0.0.1:8000/docs`-এ গিয়ে Swagger UI দিয়ে টেস্ট করতে পারবেন।

> **নোট:** `yt-dlp` কাজ করতে সিস্টেমে `ffmpeg` ইনস্টল থাকা লাগবে (`sudo apt install ffmpeg` অথবা `brew install ffmpeg`)।

## ২. Railway/Render-এ ডিপ্লয় করা

1. এই `shikhi-backend` ফোল্ডারটা একটা নতুন GitHub রিপোতে পুশ করুন।
2. Railway.app বা Render.com-এ গিয়ে "New Project → Deploy from GitHub" সিলেক্ট করুন।
3. Environment Variables-এ `GROQ_API_KEY` (আর WhatsApp চালু করলে নিচের WhatsApp ভ্যারিয়েবলগুলো) যোগ করুন।
4. Build/Start কমান্ড `Procfile` থেকে অটো ডিটেক্ট হবে (`uvicorn main:app --host 0.0.0.0 --port $PORT`)।
5. ডিপ্লয় শেষে একটা পাবলিক URL পাবেন, যেমন `https://shikhi-backend-production.up.railway.app`।

## ৩. ফ্রন্টএন্ড কানেক্ট করা

আপনার `index.html`-এর একদম নিচের দিকে `<script>` ট্যাগে এই লাইনটা খুঁজুন:

```js
const API_BASE = "https://YOUR-BACKEND-URL.up.railway.app";
```

এখানে আপনার আসল Railway/Render URL বসিয়ে দিন। এটা পরিবর্তন হওয়া মাত্রই সাইট নিজে থেকেই "ডেমো মোড" থেকে বেরিয়ে আসল ব্যাকএন্ডের সাথে কথা বলা শুরু করবে (উপরে ব্যাজে "🟢 লাইভ ব্যাকএন্ডের সাথে কানেক্টেড" দেখাবে)।

## ৪. Permission / কপিরাইট রিমাইন্ডার

আপনি আগেই বলেছেন সব ভিডিওর জন্য অনুমতি নেওয়া আছে — সেটা ঠিক আছে। ফর্মে already একটা নোট আছে ("জমা দেওয়ার আগে নিশ্চিত করুন প্রফেশনালের অনুমতি নেওয়া আছে"), সেটা রেখে দিন যাতে ভবিষ্যতে যেই ভিডিও যোগ করুক, মনে থাকে।

## এরপর কী করা যেতে পারে (পরের ধাপ)

- **Vector DB আপগ্রেড:** এখন SQLite-এ সব embedding রাখা হচ্ছে আর প্রতি প্রশ্নে সবগুলোর সাথে তুলনা করা হচ্ছে (few hundred videos পর্যন্ত ঠিক আছে)। বেশি স্কেল করলে Supabase pgvector বা Pinecone-এ যাওয়া লাগবে।
- **Facebook ভিডিও:** yt-dlp পাবলিক FB ভিডিওতে কাজ করে, তবে প্রাইভেট/লগইন-প্রয়োজনীয় ভিডিওর জন্য আলাদা হ্যান্ডলিং লাগতে পারে।
- **WhatsApp:** Meta Cloud API-তে অ্যাপ রিভিউ + ফোন নাম্বার ভেরিফিকেশন লাগবে business ব্যবহারের জন্য — শুরুতে Twilio Sandbox দিয়ে দ্রুত টেস্ট করা যায়।
- **Auth/Admin panel:** এখন `/videos` এন্ডপয়েন্ট ওপেন — প্রোডাকশনে গেলে একটা সিম্পল API key বা login বসানো উচিত।
