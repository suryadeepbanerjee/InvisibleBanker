"""
Quick start script — verifies all services are reachable before running.

Run: python scripts/check_setup.py

FIXED 2026-09-11:
- Unicode crash on Windows cp1252 console (replaced emoji with ASCII)
- Groq model updated to groq/compound-mini
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv
load_dotenv()


def check_supabase():
    print("Checking Supabase...")
    try:
        from app.core.database import get_supabase_admin
        db = get_supabase_admin()
        for table in ["users", "profiles", "documents", "knowledge", "products", "applications"]:
            res = db.table(table).select("id").limit(1).execute()
            print(f"  [OK] {table}")
        return True
    except Exception as e:
        print(f"  [FAIL] Supabase error: {e}")
        print("  -> Run schema.sql in Supabase SQL Editor first")
        return False


def check_groq():
    print("Checking Groq API...")
    try:
        from app.core.config import get_settings
        settings = get_settings()
        if not settings.groq_api_key:
            print("  [FAIL] GROQ_API_KEY not set")
            return False

        import httpx
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json={
                "model": "groq/compound-mini",  # Verified working 2026-09-11
                "messages": [{"role": "user", "content": "Say: OK"}],
                "max_tokens": 10,
            },
            timeout=15,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        print(f"  [OK] Groq API reachable (model: groq/compound-mini) -> {content.strip()[:30]!r}")
        return True
    except Exception as e:
        print(f"  [FAIL] Groq error: {e}")
        return False


def check_gemini_embedding():
    print("Checking Gemini Embedding API...")
    try:
        from app.core.config import get_settings
        from app.services.knowledge.rag import embed_text
        settings = get_settings()
        if not settings.gemini_api_key:
            print("  [FAIL] GEMINI_API_KEY not set")
            return False
        embedding = embed_text("test financial query")
        print(f"  [OK] Gemini embedding works. Dimension: {len(embedding)}")
        return True
    except Exception as e:
        print(f"  [FAIL] Embedding error: {e}")
        return False


def check_products():
    print("Checking products...")
    try:
        from app.core.database import get_supabase_admin
        db = get_supabase_admin()
        res = db.table("products").select("name, active_version").execute()
        if not res.data:
            print("  [WARN] No products found. Run: python scripts/seed_products.py")
            return False
        for p in res.data:
            print(f"  [OK] {p['name']}")
        return True
    except Exception as e:
        print(f"  [FAIL] Products error: {e}")
        return False


def check_knowledge():
    print("Checking knowledge base...")
    try:
        from app.core.database import get_supabase_admin
        db = get_supabase_admin()
        res = db.table("knowledge").select("id", count="exact").execute()
        count = res.count or 0
        if count == 0:
            print("  [WARN] No knowledge chunks. Run: python scripts/ingest_knowledge.py")
            return False
        print(f"  [OK] {count} knowledge chunks")
        return True
    except Exception as e:
        print(f"  [FAIL] Knowledge error: {e}")
        return False


def main():
    print("=" * 50)
    print("Invisible Banker -- Setup Check")
    print("=" * 50)
    print()

    results = {
        "supabase": check_supabase(),
        "groq": check_groq(),
        "gemini_embedding": check_gemini_embedding(),
        "products": check_products(),
        "knowledge": check_knowledge(),
    }

    print()
    print("=" * 50)
    all_ok = all(results.values())
    if all_ok:
        print("[OK] All checks passed! Ready to run:")
        print("   Backend:  uvicorn app.main:app --reload")
        print("   Frontend: cd ../frontend && npm run dev")
    else:
        print("[WARN] Some checks failed. Fix issues above before running.")
        failed = [k for k, v in results.items() if not v]
        print(f"  Failed: {', '.join(failed)}")
    print("=" * 50)


if __name__ == "__main__":
    main()
