"""
RAG (Retrieval Augmented Generation) লজিক:
1. ট্রান্সক্রিপ্ট chunk-এ ভাগ করা
2. চাংক ও প্রশ্নকে embedding-এ রূপান্তর (multilingual মডেল — বাংলা সাপোর্ট করে)
3. cosine similarity দিয়ে সবচেয়ে প্রাসঙ্গিক chunk খুঁজে বের করা
4. সেই chunk + প্রশ্ন Claude API-তে পাঠিয়ে উত্তর তৈরি করা
"""
import os
import numpy as np
from sentence_transformers import SentenceTransformer
from groq import Groq

import database

# বাংলা সহ ৫০+ ভাষা সাপোর্ট করে এমন হালকা multilingual embedding মডেল
_EMBED_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
_embed_model = None

# GROQ ফ্রি টিয়ারে পাওয়া যায় এমন একটা শক্তিশালী ওপেন-সোর্স মডেল।
# console.groq.com/docs/models এ গিয়ে সাপোর্টেড মডেলের সম্পূর্ণ লিস্ট দেখা যায়।
_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
_groq_client = None


def _get_embed_model() -> SentenceTransformer:
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(_EMBED_MODEL_NAME)
    return _embed_model


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY env variable সেট করা নেই।")
        _groq_client = Groq(api_key=api_key)
    return _groq_client


def chunk_text(text: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
    """সরল ক্যারেক্টার-ভিত্তিক চাংকিং, সামান্য overlap সহ যাতে প্রসঙ্গ না হারায়।"""
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = _get_embed_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()


def process_and_store_transcript(video_id: str, transcript: str):
    chunks = chunk_text(transcript)
    if not chunks:
        return
    embeddings = embed_texts(chunks)
    database.add_chunks(video_id, chunks, embeddings)


def retrieve_relevant_chunks(question: str, top_k: int = 4) -> list[dict]:
    all_chunks = database.get_all_chunks_with_meta()
    if not all_chunks:
        return []

    q_embedding = np.array(embed_texts([question])[0])
    scored = []
    for c in all_chunks:
        import json
        emb = np.array(json.loads(c["embedding"]))
        score = float(np.dot(q_embedding, emb))  # normalized -> dot product = cosine similarity
        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _score, c in scored[:top_k]]


def generate_answer(question: str) -> dict:
    relevant = retrieve_relevant_chunks(question)

    if not relevant:
        return {
            "answer": "এখনো কোনো ভিডিও থেকে যথেষ্ট তথ্য শেখা হয়নি, তাই এই প্রশ্নের উত্তর দিতে পারছি না। আগে প্রাসঙ্গিক একটা ভিডিও যোগ করুন।",
            "sources": [],
        }

    context_blocks = []
    sources = []
    seen_sources = set()
    for c in relevant:
        context_blocks.append(f"[{c['professional']} - {c['topic']}]\n{c['text']}")
        key = (c["professional"], c["topic"])
        if key not in seen_sources:
            seen_sources.add(key)
            sources.append({"professional": c["professional"], "topic": c["topic"], "link": c["link"]})

    context = "\n\n---\n\n".join(context_blocks)

    system_prompt = (
        "তুমি 'শিখি' নামের একটা AI মেন্টর। ব্যবহারকারীদের প্রশ্নের উত্তর শুধুমাত্র নিচে দেওয়া "
        "ভিডিও-ট্রান্সক্রিপ্ট প্রসঙ্গ থেকে দাও। প্রসঙ্গে না থাকা কোনো তথ্য বানিয়ে বলবে না। "
        "যদি প্রসঙ্গে যথেষ্ট তথ্য না থাকে, সেটা স্পষ্টভাবে বলে দাও। উত্তর বাংলায়, সংক্ষিপ্ত ও ব্যবহারিক হতে হবে।"
    )

    client = _get_groq_client()
    response = client.chat.completions.create(
        model=_GROQ_MODEL,
        max_tokens=600,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"প্রসঙ্গ:\n{context}\n\nপ্রশ্ন: {question}"},
        ],
    )
    answer_text = response.choices[0].message.content

    return {"answer": answer_text, "sources": sources}
