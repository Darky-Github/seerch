from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from supabase import create_client
import os
import time
import re

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

LIMIT = 30
WINDOW = 60

TITLE_BOOST = 5
KNOWN_BOOST = 30


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.client.host
    now = time.time()

    rate_store.setdefault(ip, [])
    rate_store[ip] = [t for t in rate_store[ip] if now - t < WINDOW]

    if len(rate_store[ip]) >= LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests")

    rate_store[ip].append(now)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def home():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return f.read()


def tokenize(q):
    return re.findall(r"\b\w+\b", q.lower())


def get_known():
    res = supabase.table("known_sites").select("*").execute()
    return res.data or []


def get_known_set():
    return {k["url"].lower() for k in get_known() if k.get("url")}


def score_page(page, query_words, known_set):
    text = (page.get("text") or "").lower()
    title = (page.get("title") or "").lower()
    url = (page.get("url") or "").lower()

    score = 0

    for w in query_words:
        score += text.count(w)
        if w in title:
            score += TITLE_BOOST

    if url in known_set:
        score += KNOWN_BOOST

    return max(1, min(100, score))


@app.get("/search")
def search(q: str, limit: int = 20, offset: int = 0):
    q = q.lower().strip()
    cache_key = f"{q}:{limit}:{offset}"

    if cache_key in cache:
        return cache[cache_key]

    words = tokenize(q)
    known = get_known()
    known_set = get_known_set()

    results = []

    for site in known:
        name = (site.get("name") or "").lower()
        category = (site.get("category") or "").lower()

        if q == name or q in name or q in category:
            results.append({
                "title": site["name"],
                "url": site["url"],
                "score": 100,
                "type": "known",
                "status": "known"
            })
            break

    pages_res = supabase.table("pages") \
        .select("id,title,url,text") \
        .limit(200) \
        .execute()

    pages = pages_res.data or []

    scored = []

    for page in pages:
        score = score_page(page, words, known_set)

        if score > 1:
            scored.append({
                "title": page["title"],
                "url": page["url"],
                "score": score,
                "type": "page",
                "status": "page"
            })

    scored.sort(key=lambda x: x["score"], reverse=True)

    final = results + scored[offset:offset + limit]

    cache[cache_key] = final
    return final
