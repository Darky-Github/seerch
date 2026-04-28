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
LIMIT = 30
WINDOW = 60
cache = {}


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.client.host
    now = time.time()

    if ip not in rate_store:
        rate_store[ip] = []

    rate_store[ip] = [t for t in rate_store[ip] if now - t < WINDOW]

    if len(rate_store[ip]) >= LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests")

    rate_store[ip].append(now)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def home():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return f.read()


def get_known():
    res = supabase.table("known_sites").select("*").execute()
    return res.data or []


def get_known_set():
    return {k["url"].lower() for k in get_known() if k.get("url")}

def tokenize(q):
    return re.findall(r"\b\w+\b", q.lower())

def normalize(score, max_score):
    if max_score <= 0:
        return 1
    norm = int((score / max_score) * 100)
    return max(1, min(100, norm))


def search_inverted_index(words, limit=50):
    res = supabase.table("inverted_index") \
        .select("page_id, word, weight") \
        .in_("word", words) \
        .execute()

    data = res.data or []

    scores = {}

    for row in data:
        pid = row["page_id"]
        scores[pid] = scores.get(pid, 0) + row["weight"]

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]

    if not sorted_scores:
        return []

    max_raw = sorted_scores[0][1]

    return [(pid, normalize(score, max_raw)) for pid, score in sorted_scores]


@app.get("/search")
def search(q: str, limit: int = 20, offset: int = 0):
    q_lower = q.lower().strip()
    cache_key = f"{q_lower}:{limit}:{offset}"

    if cache_key in cache:
        return cache[cache_key]

    words = tokenize(q_lower)

    known = get_known()
    known_set = get_known_set()

    results = []

    for site in known:
        name = (site.get("name") or "").lower()
        category = (site.get("category") or "").lower()

        if q_lower == name or q_lower in name or q_lower in category:
            results.append({
                "title": site.get("name"),
                "url": site.get("url"),
                "score": 100,
                "type": "known",
                "status": "known"
            })
            break

    page_hits = search_inverted_index(words, limit=100)

    if not page_hits:
        cache[cache_key] = results
        return results

    page_ids = [p[0] for p in page_hits]

    pages_res = supabase.table("pages") \
        .select("id,title,url") \
        .in_("id", page_ids) \
        .execute()

    pages = pages_res.data or []
    page_map = {p["id"]: p for p in pages}

    page_results = []

    for pid, score in page_hits:
        page = page_map.get(pid)
        if not page:
            continue

        url = (page.get("url") or "").lower()

        final_score = score

        if url in known_set:
            final_score = min(100, final_score + 30)
            status = "known"
        else:
            status = "page"

        final_score = max(1, min(100, final_score))

        page_results.append({
            "title": page.get("title"),
            "url": page.get("url"),
            "score": final_score,
            "type": "page",
            "status": status
        })

    page_results.sort(key=lambda x: x["score"], reverse=True)

    final_results = results + page_results[offset:offset + limit]

    cache[cache_key] = final_results

    return final_results
