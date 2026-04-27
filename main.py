from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from supabase import create_client
import os
import time

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


def get_known():
    res = supabase.table("known_sites").select("*").execute()
    return res.data or []


def get_verified():
    res = supabase.table("verified_sites").select("*").execute()
    data = res.data or []

    return [v for v in data if v.get("url") and v.get("name")]


def match_known(q, known):
    for site in known:
        name = (site.get("name") or "").lower()
        url = (site.get("url") or "").lower()
        category = (site.get("category") or "").lower()

        if q == name or name in q or q in name or q in url or q in category:
            return site
    return None


@app.get("/", response_class=HTMLResponse)
def home():
    with open("frontend/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/search")
def search(q: str):
    q_lower = q.lower().strip()

    if q_lower in cache:
        return cache[q_lower]

    known = get_known()
    verified = get_verified()

    verified_set = {v["url"].lower() for v in verified}

    results = []

    match = match_known(q_lower, known)

    if match:
        url = match["url"].lower()
        is_verified = url in verified_set

        results.append({
            "title": match["name"],
            "url": match["url"],
            "score": 100,
            "type": "known",
            "status": "secure" if is_verified else "known"
        })

    page_res = supabase.table("pages") \
        .select("title,url,text") \
        .ilike("text", f"%{q_lower}%") \
        .limit(20) \
        .execute()

    pages = page_res.data or []

    page_results = []

    for page in pages:
        text = (page.get("text") or "").lower()
        title = page.get("title") or ""
        url = (page.get("url") or "").lower()

        score = text.count(q_lower)

        if q_lower in title.lower():
            score += 5

        if url in verified_set:
            score += 10
            status = "secure"
        else:
            status = "page"

        if score > 0:
            page_results.append({
                "title": title,
                "url": url,
                "score": score,
                "type": "page",
                "status": status
            })

    page_results.sort(key=lambda x: x["score"], reverse=True)

    final_results = results + page_results[:9]

    cache[q_lower] = final_results

    return final_results
