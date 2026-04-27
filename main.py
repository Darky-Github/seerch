from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
import os
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://darky-github.github.io",
        "https://darky-github.github.io/seerch-engine"
    ],
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
    return supabase.table("known_sites").select("*").execute().data


def get_verified():
    return supabase.table("verified_sites").select("*").execute().data


def match_known(q_lower, known):
    for site in known:
        name = (site.get("name") or "").lower()
        url = (site.get("url") or "").lower()
        category = (site.get("category") or "").lower()
        desc = (site.get("description") or "").lower()

        if (
            q_lower == name or
            name in q_lower or
            q_lower in name or
            q_lower in url or
            q_lower in category or
            any(word in name for word in q_lower.split())
        ):
            return site

    return None


@app.get("/search")
def search(q: str):
    q_lower = q.lower().strip()

    known = get_known()
    verified = get_verified()

    match = match_known(q_lower, known)

    if match:
        return [{
            "title": match["name"],
            "url": match["url"],
            "score": 9999,
            "type": "known",
            "category": match.get("category", "")
        }]

    data = supabase.table("pages").select("*").execute().data

    results = []

    for page in data:
        text = page.get("text", "").lower()
        title = page.get("title", "")
        url = page.get("url", "")

        score = text.count(q_lower)

        if score > 0:
            domain = url.split("/")[2] if "://" in url else ""

            for v in verified:
                if v["domain"] == domain:
                    score += 5

            results.append({
                "title": title,
                "url": url,
                "score": score,
                "type": "page"
            })

    results.sort(key=lambda x: x["score"], reverse=True)

    return results[:10]
