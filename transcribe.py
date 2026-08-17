"""
YouTube/Facebook ভিডিও থেকে অডিও ডাউনলোড করে Whisper দিয়ে ট্রান্সক্রিপ্ট বের করা হয়।
faster-whisper ব্যবহার করা হয়েছে কারণ এটা CPU-তেও তুলনামূলক দ্রুত।
"""
import os
import tempfile
import uuid

import yt_dlp
from faster_whisper import WhisperModel

# "base" মডেল দিয়ে শুরু করা ভালো — গতি ও কোয়ালিটির মধ্যে ব্যালেন্স।
# সার্ভারে RAM/CPU বেশি থাকলে "small" বা "medium" ব্যবহার করতে পারেন আরও ভালো ফলাফলের জন্য।
_WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
_model = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(_WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def download_audio(video_url: str) -> str:
    """yt-dlp দিয়ে অডিও ডাউনলোড করে temp ফাইল পাথ ফেরত দেয়।"""
    out_dir = tempfile.mkdtemp()
    out_path = os.path.join(out_dir, f"{uuid.uuid4()}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": out_path,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",
        }],
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    # postprocessor .mp3 এক্সটেনশনে সেভ করে
    mp3_path = out_path.replace("%(ext)s", "mp3")
    if not os.path.exists(mp3_path):
        # fallback: ডিরেক্টরিতে যা পাওয়া যায় তাই খুঁজে বের করা
        for f in os.listdir(out_dir):
            if f.endswith(".mp3"):
                mp3_path = os.path.join(out_dir, f)
                break
    return mp3_path


def transcribe_audio(audio_path: str) -> str:
    model = _get_model()
    segments, _info = model.transcribe(audio_path, language=None, vad_filter=True)
    text = " ".join(seg.text.strip() for seg in segments)
    return text.strip()


def transcribe_video(video_url: str) -> str:
    """ফুল পাইপলাইন: লিংক -> অডিও -> ট্রান্সক্রিপ্ট। ব্যর্থ হলে exception raise করে।"""
    audio_path = download_audio(video_url)
    try:
        return transcribe_audio(audio_path)
    finally:
        # temp ফাইল ক্লিনআপ
        try:
            os.remove(audio_path)
        except OSError:
            pass
