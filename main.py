from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from supabase import create_client
import os
import time
import meilisearch

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

meili = meilisearch.Client(
    os.getenv("MEILI_HOST"),
    os.getenv("MEILI_KEY")
)

index = meili.index("pages")

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


@app.get("/search")
def search(q: str, limit: int = 20, offset: int = 0):
    q_lower = q.lower().strip()
    cache_key = f"{q_lower}:{limit}:{offset}"

    if cache_key in cache:
        return cache[cache_key]

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

    search_res = index.search(q_lower, {
        "limit": limit + offset
    })

    hits = search_res.get("hits", [])

    page_results = []

    for hit in hits:
        url = (hit.get("url") or "").lower()

        if url in known_set:
            score = 100
            status = "known"
        else:
            score = 80
            status = "page"

        page_results.append({
            "title": hit.get("title"),
            "url": hit.get("url"),
            "score": score,
            "type": "page",
            "status": status
        })

    final_results = results + page_results[offset:offset + limit]

    cache[cache_key] = final_results

    return final_results
