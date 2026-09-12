"""
Crawl trusted financial sources (P0) to ingest into knowledge base.

Features:
- Respects robots.txt
- 2-second delay per host
- Retries with backoff
- Content hashing to avoid duplicates
- Stores embeddings in `knowledge` table
- Updates `sources` table with status
"""
import sys
import os
import time
import hashlib
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
import httpx
from bs4 import BeautifulSoup
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()

from app.core.database import get_supabase_admin
from app.services.knowledge.rag import embed_text

USER_AGENT = "InvisibleBankerBot/1.0"
DELAY_BETWEEN_REQUESTS = 2.0  # seconds

db = get_supabase_admin()
robot_parsers = {}

def get_robot_parser(base_url):
    parsed = urlparse(base_url)
    domain = f"{parsed.scheme}://{parsed.netloc}"
    if domain not in robot_parsers:
        rp = RobotFileParser()
        robots_url = f"{domain}/robots.txt"
        try:
            # We don't want to block forever on robots.txt
            rp.set_url(robots_url)
            rp.read()
        except Exception as e:
            print(f"  [WARN] Failed to fetch robots.txt for {domain}: {e}")
        robot_parsers[domain] = rp
    return robot_parsers[domain]

def is_allowed(url):
    rp = get_robot_parser(url)
    return rp.can_fetch(USER_AGENT, url)

def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    words = text.split()
    if len(words) <= chunk_size:
        return [text]
    
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = ' '.join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks

def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def fetch_and_extract(url, retries=3):
    headers = {"User-Agent": USER_AGENT}
    
    for attempt in range(retries):
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, headers=headers, follow_redirects=True)
                resp.raise_for_status()
                
                soup = BeautifulSoup(resp.text, "html.parser")
                # Remove scripts, styles, nav, headers, footers
                for el in soup(["script", "style", "nav", "header", "footer", "aside", "noscript"]):
                    el.extract()
                
                # Extract text and clean up whitespace
                text = soup.get_text(separator=' ')
                text = re.sub(r'\s+', ' ', text).strip()
                return text
        except Exception as e:
            print(f"  [WARN] Fetch failed for {url} on attempt {attempt+1}: {e}")
            time.sleep(DELAY_BETWEEN_REQUESTS * (2 ** attempt)) # exponential backoff
    
    return None

def main():
    print("Starting P0 source crawler...")
    
    # Get P0 sources
    sources_res = db.table("sources").select("*").eq("crawl_enabled", True).execute()
    sources = sources_res.data
    
    print(f"Found {len(sources)} P0 sources to crawl.")
    
    total_ingested = 0
    total_skipped = 0
    
    for source in sources:
        print(f"\nCrawling source: {source['name']} ({source['base_url']})")
        
        subpaths = source.get("crawl_subpaths", [])
        if not subpaths:
            subpaths = [source["base_url"]]
            
        source_chunks_count = 0
        status = "SUCCESS"
        
        for url in subpaths:
            # Check robots.txt
            if not is_allowed(url):
                print(f"  [SKIP] Blocked by robots.txt: {url}")
                status = "BLOCKED"
                continue
                
            print(f"  Fetching: {url}")
            time.sleep(DELAY_BETWEEN_REQUESTS)
            
            text = fetch_and_extract(url)
            if not text:
                print(f"  [ERROR] Could not extract content from {url}")
                status = "FAILED"
                continue
                
            if len(text) < 100:
                print(f"  [SKIP] Content too short for {url}")
                continue
                
            chunks = chunk_text(text)
            print(f"  Extracted {len(chunks)} chunks.")
            
            for i, chunk in enumerate(chunks):
                c_hash = content_hash(chunk)
                
                # Dedup check
                existing = db.table("knowledge").select("id").eq("content_hash", c_hash).execute()
                if existing.data:
                    total_skipped += 1
                    continue
                
                # Embed and insert
                embedding = embed_text(chunk)
                
                db.table("knowledge").insert({
                    "title": f"{source['name']} - Content {i+1}",
                    "authority": source["name"],
                    "source_url": url,
                    "source_type": source["category"],
                    "content": chunk,
                    "embedding": embedding,
                    "version": 1,
                    "content_hash": c_hash,
                    "metadata": {"chunk_index": i, "total_chunks": len(chunks), "source_id": source["id"]},
                }).execute()
                
                source_chunks_count += 1
                total_ingested += 1
                
        # Update source status
        if source_chunks_count == 0 and status == "SUCCESS":
            status = "UNAVAILABLE"
            
        # Update source status
        db.table("sources").update({
            "last_crawled": "now()",
            "last_crawl_status": status,
            "chunks_count": source_chunks_count + source.get("chunks_count", 0)
        }).eq("id", source["id"]).execute()
        
        print(f"  Finished {source['name']}. Ingested {source_chunks_count} new chunks.")
        
    print(f"\nCrawler finished!")
    print(f"Total new chunks ingested: {total_ingested}")
    print(f"Total chunks skipped (dedup): {total_skipped}")

if __name__ == "__main__":
    main()
