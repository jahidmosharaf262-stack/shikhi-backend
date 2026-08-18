"""
YouTube ভিডিও থেকে ট্রান্সক্রিপ্ট সংগ্রহ — ৩ লেয়ারের ব্যাকআপ সিস্টেম।

কেন এই পরিবর্তন?
  আগের ভার্সনে `youtube_transcript_api` ব্যবহার হতো, যেটা YouTube-এর একটা
  আলাদা (undocumented) ইন্টারনাল endpoint কল করে। Railway/AWS/GCP-এর মতো
  cloud সার্ভারের IP থেকে অনেক বট ট্রাফিক যাওয়ায় YouTube সেগুলো প্রায়ই
  429 (Too Many Requests) দিয়ে ব্লক করে দেয়।

  সমাধান হিসেবে এখানে `yt-dlp` ব্যবহার করা হয়েছে — এটা রেগুলার ভিডিও পেজ
  থেকে ডেটা টানে (ব্রাউজারের মতো), তাই সহজে ব্লক হয় না। আর যদি ভিডিওতে
  কোনো সাবটাইটেল/ক্যাপশনই না থাকে, তাহলে অডিও ডাউনলোড করে Whisper দিয়ে
  ট্রান্সক্রাইব করা হয়।

ধাপগুলো (ক্রমানুসারে চেষ্টা হয়):
  ১. yt-dlp দিয়ে ম্যানুয়াল সাবটাইটেল (সবচেয়ে নির্ভুল)
  ২. yt-dlp দিয়ে auto-generated সাবটাইটেল
  ৩. yt-dlp দিয়ে অডিও ডাউনলোড + Whisper দিয়ে স্পিচ-টু-টেক্সট (fallback)

`main.py`-তে কোনো পরিবর্তনের দরকার নেই — ফাংশনের নাম, প্যারামিটার এবং
রিটার্ন টাইপ (str) আগের মতোই আছে: transcribe_video(video_url) -> str
"""
import os
import re
import glob
import logging
import tempfile

import yt_dlp

logger = logging.getLogger(__name__)

PREFERRED_LANGS = ["bn", "en", "hi"]


def extract_video_id(url: str) -> str | None:
    """YouTube URL থেকে ১১-ক্যারেক্টারের video ID বের করা।"""
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _pick_subtitle_url(subs_dict: dict) -> tuple[str, str] | None:
    """subs_dict = info['subtitles'] বা info['automatic_captions']
    থেকে পছন্দের ভাষা অনুযায়ী সাবটাইটেলের URL বের করা।
    রিটার্ন করে (lang_code, subtitle_url) অথবা None।
    """
    if not subs_dict:
        return None

    # প্রথমে পছন্দের ভাষাগুলো ক্রম অনুযায়ী চেক করা
    for lang in PREFERRED_LANGS:
        # exact match (bn) অথবা variant (bn-BD, en-US ইত্যাদি)
        for code in subs_dict:
            if code == lang or code.startswith(f"{lang}-"):
                formats = subs_dict[code]
                vtt = next((f for f in formats if f.get("ext") == "vtt"), formats[0])
                return code, vtt["url"]

    # পছন্দের ভাষা কিছুই না থাকলে, যা পাওয়া যায় তাই নেওয়া
    first_lang = next(iter(subs_dict))
    formats = subs_dict[first_lang]
    vtt = next((f for f in formats if f.get("ext") == "vtt"), formats[0])
    return first_lang, vtt["url"]


def _vtt_to_text(vtt_content: str) -> str:
    """VTT সাবটাইটেল কনটেন্ট থেকে শুধু টেক্সট বের করা (টাইমস্ট্যাম্প, নাম্বারিং বাদ)।"""
    lines = vtt_content.splitlines()
    text_lines = []
    seen = set()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line:  # টাইমস্ট্যাম্প লাইন
            continue
        if line.isdigit():  # সিকোয়েন্স নাম্বার
            continue
        # ইনলাইন টাইমিং ট্যাগ যেমন <00:00:01.500> বাদ দেওয়া
        clean = re.sub(r"<[^>]+>", "", line)
        clean = clean.strip()
        if not clean:
            continue
        # yt-dlp auto-caption VTT-তে প্রায়ই একই লাইন বারবার (rolling caption) আসে
        if clean in seen:
            continue
        seen.add(clean)
        text_lines.append(clean)
    return " ".join(text_lines)


def _try_get_subtitles_via_ytdlp(video_url: str) -> str | None:
    """yt-dlp দিয়ে ম্যানুয়াল -> auto-generated সাবটাইটেল বের করার চেষ্টা।
    সফল হলে ট্রান্সক্রিপ্ট টেক্সট রিটার্ন করে, না পেলে None।
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": False,
        "writeautomaticsub": False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("yt-dlp দিয়ে ভিডিও ইনফো আনতে সমস্যা: %s", e)
        return None

    # ১. ম্যানুয়াল সাবটাইটেল
    picked = _pick_subtitle_url(info.get("subtitles") or {})
    source = "ম্যানুয়াল"

    # ২. না পেলে auto-generated
    if picked is None:
        picked = _pick_subtitle_url(info.get("automatic_captions") or {})
        source = "auto-generated"

    if picked is None:
        return None

    lang_code, sub_url = picked
    logger.info("%s সাবটাইটেল পাওয়া গেছে, ভাষা=%s", source, lang_code)

    import urllib.request

    try:
        with urllib.request.urlopen(sub_url, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:  # noqa: BLE001
        logger.warning("সাবটাইটেল ফাইল ডাউনলোড করতে সমস্যা: %s", e)
        return None

    text = _vtt_to_text(raw)
    return text.strip() if text.strip() else None


def _transcribe_via_whisper(video_url: str) -> str:
    """সাবটাইটেল না থাকলে: অডিও ডাউনলোড করে Whisper দিয়ে ট্রান্সক্রাইব।
    এটা ধীর, কিন্তু যেকোনো ভিডিওর জন্য কাজ করে।
    """
    import whisper  # openai-whisper প্যাকেজ; requirements.txt এ যোগ করতে হবে

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_template = os.path.join(tmp_dir, "audio.%(ext)s")
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                }
            ],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"অডিও ডাউনলোড করতে ব্যর্থ: {e}") from e

        audio_files = glob.glob(os.path.join(tmp_dir, "audio.*"))
        if not audio_files:
            raise ValueError("অডিও ফাইল ডাউনলোড হলেও খুঁজে পাওয়া যায়নি।")
        audio_path = audio_files[0]

        logger.info("Whisper মডেল লোড হচ্ছে (base)...")
        model = whisper.load_model("base")  # ছোট মডেল -> Railway তে দ্রুত ও কম মেমরি
        logger.info("Whisper দিয়ে ট্রান্সক্রাইব শুরু হচ্ছে...")
        result = model.transcribe(audio_path, language=None)  # ভাষা auto-detect

    text = (result.get("text") or "").strip()
    if not text:
        raise ValueError("Whisper থেকেও কোনো টেক্সট পাওয়া যায়নি।")
    return text


def transcribe_video(video_url: str) -> str:
    """মূল এন্ট্রি পয়েন্ট — main.py এখান থেকেই কল করে।

    ক্রম:
      ১. yt-dlp দিয়ে সাবটাইটেল (manual > auto)
      ২. না পেলে Whisper দিয়ে অডিও থেকে ট্রান্সক্রাইব
    """
    video_id = extract_video_id(video_url)
    if not video_id:
        raise ValueError(f"YouTube video ID খুঁজে পাওয়া যায়নি: {video_url}")

    logger.info("ট্রান্সক্রিপ্ট আনা হচ্ছে video_id=%s", video_id)

    # ধাপ ১ ও ২: yt-dlp দিয়ে সাবটাইটেল
    text = _try_get_subtitles_via_ytdlp(video_url)
    if text:
        return text

    logger.info("সাবটাইটেল পাওয়া যায়নি, Whisper দিয়ে অডিও ট্রান্সক্রিপশনে যাওয়া হচ্ছে...")

    # ধাপ ৩: Whisper fallback
    return _transcribe_via_whisper(video_url)
