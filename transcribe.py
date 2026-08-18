"""
YouTube ভিডিও থেকে সরাসরি সাবটাইটেল/ট্রান্সক্রিপ্ট সংগ্রহ।
youtube-transcript-api ব্যবহার করা হয়েছে — অডিও ডাউনলোড বা Whisper-এর দরকার নেই।
এটা অনেক দ্রুত, হালকা, এবং Railway-এর ফ্রি টিয়ারেও চলে।
"""
import re
import logging

from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)


def extract_video_id(url: str) -> str | None:
    """YouTube URL থেকে ১১-ক্যারেক্টারের video ID বের করা।
    সাপোর্টেড ফরম্যাট:
      - https://www.youtube.com/watch?v=XXXXX
      - https://youtu.be/XXXXX
      - https://www.youtube.com/embed/XXXXX
      - https://www.youtube.com/v/XXXXX
    """
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/)([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def transcribe_video(video_url: str) -> str:
    """YouTube সাবটাইটেল থেকে ট্রান্সক্রিপ্ট নেওয়া।
    প্রথমে ম্যানুয়াল সাবটাইটেল খোঁজে, না পেলে auto-generated।
    ভাষা অগ্রাধিকার: বাংলা > ইংরেজি > হিন্দি > যেকোনো ভাষা।
    """
    video_id = extract_video_id(video_url)
    if not video_id:
        raise ValueError(f"YouTube video ID খুঁজে পাওয়া যায়নি: {video_url}")

    logger.info("ট্রান্সক্রিপ্ট আনা হচ্ছে video_id=%s", video_id)

    preferred_langs = ["bn", "en", "hi"]
    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    transcript = None

    # ১. প্রথমে ম্যানুয়ালি তৈরি সাবটাইটেল খোঁজা (সবচেয়ে নির্ভুল)
    try:
        transcript = transcript_list.find_manually_created_transcript(preferred_langs)
        logger.info("ম্যানুয়াল সাবটাইটেল পাওয়া গেছে: %s", transcript.language_code)
    except Exception:
        pass

    # ২. না পেলে auto-generated সাবটাইটেল
    if transcript is None:
        try:
            transcript = transcript_list.find_generated_transcript(preferred_langs)
            logger.info("Auto-generated সাবটাইটেল পাওয়া গেছে: %s", transcript.language_code)
        except Exception:
            pass

    # ৩. তাও না পেলে যেকোনো ভাষার সাবটাইটেল নেওয়া
    if transcript is None:
        for t in transcript_list:
            transcript = t
            logger.info("ফলব্যাক সাবটাইটেল ব্যবহার হচ্ছে: %s", t.language_code)
            break

    if transcript is None:
        raise ValueError(
            f"এই ভিডিওতে কোনো সাবটাইটেল/ক্যাপশন পাওয়া যায়নি (video_id={video_id})। "
            "ভিডিওতে সাবটাইটেল চালু আছে কিনা যাচাই করুন।"
        )

    entries = transcript.fetch()
    text = " ".join(entry["text"] for entry in entries)
    return text.strip()
