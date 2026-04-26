from fastapi import FastAPI
from supabase import create_client
import os

app = FastAPI()

supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

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

    return sorted(results, key=lambda x: x["score"], reverse=True)[:10]