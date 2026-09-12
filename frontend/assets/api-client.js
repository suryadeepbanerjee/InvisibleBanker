/**
 * Thin fetch wrapper over the real Invisible Banker FastAPI backend.
 * No mock data, no fallback fixtures — every function either returns
 * real backend JSON or throws, and callers must render a real error/empty
 * state. Matches backend/app/models/schemas.py and backend/app/api/routes/*.
 */
(function () {
  const BASE = window.APP_CONFIG.API_BASE_URL.replace(/\/$/, "");

  async function request(path, options = {}) {
    let res;
    try {
      res = await fetch(`${BASE}${path}`, {
        headers: options.body instanceof FormData
          ? undefined
          : { "Content-Type": "application/json" },
        ...options,
      });
    } catch (networkErr) {
      throw new ApiError(
        `Could not reach the backend at ${BASE}. Is it running? (${networkErr.message})`,
        0,
        null
      );
    }

    let data = null;
    const text = await res.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }

    if (!res.ok) {
      const detail = (data && data.detail) ? data.detail : res.statusText;
      throw new ApiError(detail || `Request failed (${res.status})`, res.status, data);
    }
    return data;
  }

  class ApiError extends Error {
    constructor(message, status, data) {
      super(message);
      this.status = status;
      this.data = data;
    }
  }

  window.InvisibleBankerAPI = {
    ApiError,

    // POST /api/chat/  → ChatResponse
    sendChatMessage({ message, user_id, conversation_id, application_id, language }) {
      return request("/chat/", {
        method: "POST",
        body: JSON.stringify({ message, user_id, conversation_id, application_id, language }),
      });
    },

    // GET /api/chat/conversation/{id}/messages
    getConversationMessages(conversationId, limit = 50) {
      return request(`/chat/conversation/${encodeURIComponent(conversationId)}/messages?limit=${limit}`);
    },

    // POST /api/chat/conversation/new
    startNewConversation(userId, language = "en-IN") {
      const qs = new URLSearchParams({ user_id: userId, language });
      return request(`/chat/conversation/new?${qs.toString()}`, { method: "POST" });
    },

    // GET /api/chat/conversation/{id}/research-status
    getResearchStatus(conversationId) {
      return request(`/chat/conversation/${encodeURIComponent(conversationId)}/research-status`);
    },

    // POST /api/eligibility/check  → EligibilityResponse
    checkEligibility(userId, applicationId) {
      return request("/eligibility/check", {
        method: "POST",
        body: JSON.stringify({ user_id: userId, application_id: applicationId }),
      });
    },

    // GET /api/workflow/application/{id}
    getApplication(applicationId) {
      return request(`/workflow/application/${encodeURIComponent(applicationId)}`);
    },

    // GET /api/workflow/user/{id}/latest
    getLatestApplication(userId) {
      return request(`/workflow/user/${encodeURIComponent(userId)}/latest`);
    },

    // POST /api/workflow/application/{id}/select-product
    selectProduct(applicationId, productId) {
      const qs = new URLSearchParams({ product_id: productId });
      return request(`/workflow/application/${encodeURIComponent(applicationId)}/select-product?${qs.toString()}`, {
        method: "POST",
      });
    },

    // POST /api/documents/upload  (multipart)
    uploadDocument(file, userId, applicationId) {
      const form = new FormData();
      form.append("file", file);
      form.append("user_id", userId);
      form.append("application_id", applicationId);
      return request("/documents/upload", { method: "POST", body: form });
    },

    // POST /api/voice/transcribe  (multipart audio)
    transcribeAudio(audioBlob, filename = "recording.webm") {
      const form = new FormData();
      form.append("audio", audioBlob, filename);
      return request("/voice/transcribe", { method: "POST", body: form });
    },
  };
})();
