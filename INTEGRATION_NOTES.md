# Invisible Banker — Frontend Integration Notes

Written for your Obsidian vault. I don't have access to your actual vault
(no filesystem/plugin access from here), so drop this file in yourself —
I'm not going to pretend I updated something I can't reach.

## What changed

`frontend/index.html` and `frontend/chat.html` are your teammate's files,
UI/CSS/animations untouched. What changed is the JavaScript:

- **`frontend/assets/config.js`** — `API_BASE_URL`, the static-HTML
  equivalent of `VITE_API_BASE_URL` (there's no Vite build here, so
  `import.meta.env` isn't available — this is the honest equivalent, not
  the literal thing).
- **`frontend/assets/api-client.js`** — one function per real backend
  route, matching `backend/app/models/schemas.py` and
  `backend/app/api/routes/*.py` exactly. No mock data, no fallback
  fixtures anywhere in it.
- **`chat.html`'s inline `<script>`** — rewritten. Removed:
  `simulateAIResponse`, the `mockQuery` voice simulator, the fake
  ₹5,00,000 / 14% p.a. option cards, the hardcoded audit trail, the fake
  Video-KYC panel. Replaced with real backend calls.

## Deviation you should know about

The old "Evidence" tab was a fake Video-KYC scanner — your backend has
**no KYC/video endpoint at all**. I repurposed that tab's content into
real source/evidence rendering (`EligibilityResponse.evidence_summary`),
since the tab was already labeled "Evidence" and you explicitly asked for
real evidence rendering. That's a content swap inside an existing tab,
not a layout redesign — flagging it because you said don't redesign, and
this is the one place I overrode that on purpose.

The option cards no longer show tenure or interest rate. Your backend's
`ProductRecommendation` model doesn't have those fields — MUDRA loans in
particular have bank-set rates, not fixed ones. Showing tenure/rate would
mean inventing numbers, which is exactly what you told me to stop doing.

## Endpoint contract — verified against a live FastAPI boot

I booted `app.main:app` in a clean venv and hit every route with
`TestClient`. All match what `api-client.js` calls, byte for byte:

| Frontend calls | Backend has it |
|---|---|
| `POST /api/chat/` | ✅ |
| `GET /api/chat/conversation/{id}/messages` | ✅ |
| `POST /api/chat/conversation/new` | ✅ |
| `GET /api/chat/conversation/{id}/research-status` | ✅ |
| `POST /api/eligibility/check` | ✅ |
| `GET /api/workflow/application/{id}` | ✅ |
| `GET /api/workflow/user/{id}/latest` | ✅ |
| `POST /api/workflow/application/{id}/select-product` | ✅ |
| `POST /api/voice/transcribe` | ✅ |
| `POST /api/documents/upload` | ✅ |

With dummy Supabase credentials, every endpoint dispatched to the right
handler and failed *only* at the Supabase network call
(`httpx.ConnectError`) — not a 404, not a schema mismatch. That's as far
as I can verify without your real Supabase project.

## What is NOT tested, and why — read this before you assume it works

I have no Supabase project, no Groq/Gemini key, no Sarvam key, and no
network path to any of those services from my sandbox. So none of these
were run against your real stack:

- PMAY / business loan / UPI query correctness
- Conversation persistence across refresh (code path is real; unverified live)
- Real source/evidence rendering with actual RAG chunks
- Language toggle actually changing LLM output
- Voice transcription round-trip
- Document upload extraction

The code paths are real and match your contracts. "Tested end-to-end" is
not something I can honestly claim — that requires running it against
your live Supabase + LLM keys yourself.

## To actually run and test this

1. `cd backend && cp .env.example .env` — fill in real
   `supabase_url`, `supabase_service_role_key`, `groq_api_key` (or
   `gemini_api_key`), `sarvam_api_key`.
2. `pip install -r requirements.txt` (in a venv; requirements.txt pulls
   in `pdfplumber`, `crawl4ai`, etc. — heavier than the bare minimum I
   installed for the smoke test).
3. `python scripts/init_db.py` then `python scripts/seed_products.py`
   and `python scripts/seed_sources.py` — without seeded products,
   `/api/eligibility/check` returns 404 by design (`backend/app/api/routes/eligibility.py`).
4. `uvicorn app.main:app --reload` — default `http://localhost:8000`.
5. Serve `frontend/` as static files (e.g. `python -m http.server 5500`
   from inside `frontend/`) and open `index.html`. If your backend isn't
   on `localhost:8000`, edit `frontend/assets/config.js`.
6. Run the 8 scenarios in your original ask yourself, watching the
   browser console and the FastAPI logs — that's the actual end-to-end
   test, and it needs your credentials, not mine.

## Left untouched, worth your attention

- The old Vite/React frontend (`frontend/src/*.jsx`, `frontend/package.json`,
  etc. from your original zip) is **not included in this package** — you
  asked me to replace the frontend with the teammate's HTML pages, so I
  packaged only those. Your original React app still exists wherever you
  keep the source; it's now unused unless you want it removed for real or
  `render.yaml` updated to serve static files instead of a Vite build. I
  didn't touch `render.yaml` — deployment config wasn't in scope and I
  don't want to break your deploy without you deciding that.
