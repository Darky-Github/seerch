from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client
import os
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://darky-github.github.io/seerch-engine/",
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

requests = {}
LIMIT = 30
WINDOW = 60  # seconds

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.client.host
    now = time.time()

    if ip not in requests:
        requests[ip] = []

    requests[ip] = [t for t in requests[ip] if now - t < WINDOW]

    if len(requests[ip]) >= LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests")

    requests[ip].append(now)

    return await call_next(request)
    
@app.get("/search")
def search(q: str):
    data = supabase.table("pages").select("*").execute().data

    results = []

    for page in data:
        text = page.get("text", "").lower()
        title = page.get("title", "")
        url = page.get("url", "")

        score = text.count(q.lower())

        if score > 0:
            results.append({
                "title": title,
                "url": url,
                "score": score
            })

    results.sort(key=lambda x: x["score"], reverse=True)

    return results[:10]
