/**
 * Runtime config for the static (non-Vite) frontend.
 *
 * These pages are plain HTML/JS, not a Vite build, so `import.meta.env`
 * is not available at runtime. This file is the equivalent knob:
 * edit API_BASE_URL (or override it before this script loads) to point
 * at your FastAPI backend. It mirrors the FRONTEND_API_BASE_URL /
 * VITE_API_BASE_URL value from frontend/.env.example in the React app.
 */
window.APP_CONFIG = {
  // Local FastAPI dev server default. Change for staging/prod, or set
  // window.APP_CONFIG before this script runs to override without editing
  // this file (e.g. injected by a deploy step).
  API_BASE_URL: window.APP_CONFIG?.API_BASE_URL || "http://localhost:8000/api",
};
