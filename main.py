from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from supabase import create_client
import os
import time
import re
from math import log

app = FastAPI()

app.mount("/static", StaticFiles(directory="frontend"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

rate_store = {}
cache = {}
cache_time = {}

LIMIT = 30
WINDOW = 60
CACHE_TTL = 300

TITLE_BOOST = 3
KNOWN_BOOST = 30

DOC_FREQ = {}
DOC_COUNT = 0


# ---------------- TOKENIZE ----------------

STOPWORDS = {"the", "is", "and", "a", "to", "of", "in"}


def tokenize(text):
    return [w for w in re.findall(r"\b\w+\b", text.lower()) if w not in STOPWORDS]


# ---------------- IDF ----------------

def build_idf():
    global DOC_FREQ, DOC_COUNT

    res = supabase.table("inverted_index").select("word,page_id").execute()
    rows = res.data or []

    DOC_COUNT = len(set(r["page_id"] for r in rows))

    for r in rows:
        w = r["word"]
        DOC_FREQ[w] = DOC_FREQ.get(w, set())
        DOC_FREQ[w].add(r["page_id"])

    for w in DOC_FREQ:
        DOC_FREQ[w] = len(DOC_FREQ[w])


def idf(word):
    df = DOC_FREQ.get(word, 0)
    return log((DOC_COUNT + 1) / (df + 1)) + 1


build_idf()


# ---------------- RATE LIMIT ----------------

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.headers.get("x-forwarded-for", request.client.host)
    now = time.time()

    rate_store.setdefault(ip, [])
    rate_store[ip] = [t for t in rate_store[ip] if now - t < WINDOW]

    if len(rate_store[ip]) >= LIMIT:
        raise HTTPException(status_code=429)

    rate_store[ip].append(now)
    return await call_next(request)


# ---------------- FRONTEND ----------------

@app.get("/", response_class=HTMLResponse)
def home():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return f.read()


# ---------------- SEARCH ----------------

def get_candidate_pages(words):
    res = supabase.table("inverted_index") \
        .select("page_id, weight, word") \
        .in_("word", words) \
        .execute()

    data = res.data or []

    scores = {}

    for row in data:
        pid = row["page_id"]
        w = row["word"]
        scores[pid] = scores.get(pid, 0) + row["weight"] * idf(w)

    return scores


def fetch_pages(ids):
    if not ids:
        return []

    res = supabase.table("pages") \
        .select("id,title,url,text") \
        .in_("id", ids) \
        .execute()

    return res.data or []


def make_snippet(text, query_words):
    words = text.split()

    for i, w in enumerate(words):
        if any(q in w.lower() for q in query_words):
            start = max(0, i - 10)
            return " ".join(words[start:start + 60]) + "..."

    return " ".join(words[:60]) + "..."


@app.get("/search")
def search(q: str, limit: int = 20):

    q = q.lower().strip()
    words = tokenize(q)

    cache_key = q

    if cache_key in cache and time.time() - cache_time[cache_key] < CACHE_TTL:
        return cache[cache_key]

    scores = get_candidate_pages(words)

    # LIMIT EARLY (important)
    top_ids = sorted(scores, key=scores.get, reverse=True)[:100]

    pages = fetch_pages(top_ids)

    results = []

    for p in pages:
        score = scores.get(p["id"], 0)

        results.append({
            "title": p["title"],
            "url": p["url"],
            "score": round(score, 2),
            "snippet": make_snippet(p.get("text", ""), words)
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    response = {"results": results[:limit]}

    cache[cache_key] = response
    cache_time[cache_key] = time.time()

    return response
