FROM python:3.11-slim

# youtube-transcript-api ব্যবহার হচ্ছে, তাই ffmpeg/av লাইব্রেরি আর দরকার নেই।
# এতে Docker ইমেজ অনেক ছোট ও দ্রুত বিল্ড হবে।

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
