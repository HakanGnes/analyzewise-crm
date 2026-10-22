const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    let detail = `İstek başarısız oldu (${response.status}).`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      // response body wasn't JSON — keep the generic message
    }
    throw new Error(detail);
  }
  return response.json();
}

export function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);
  return request("/api/upload", { method: "POST", body: formData });
}

export function startDemo() {
  return request("/api/demo", { method: "POST" });
}

// Fire-and-forget: wakes a sleeping free-tier backend while the visitor is
// still reading the landing page, so the first real request is faster.
export function warmUpBackend() {
  fetch(`${API_BASE}/api/health`).catch(() => {});
}

export function deleteSession(sessionId) {
  return request(`/api/sessions/${sessionId}`, { method: "DELETE" });
}

export function getOverview(sessionId) {
  return request(`/api/overview?session_id=${sessionId}`);
}

export function getSegments(sessionId, { k, auto } = {}) {
  const params = new URLSearchParams({ session_id: sessionId });
  if (auto) params.set("auto", "true");
  else if (k) params.set("k", String(k));
  return request(`/api/segments?${params}`);
}

export function getCltv(sessionId, approach = "single") {
  return request(`/api/cltv?session_id=${sessionId}&approach=${approach}`);
}

export function getCltvEvaluate(sessionId, approach = "single") {
  return request(`/api/cltv/evaluate?session_id=${sessionId}&approach=${approach}`);
}

export function getChurn(sessionId) {
  return request(`/api/churn?session_id=${sessionId}`);
}

export function getChurnEvaluate(sessionId) {
  return request(`/api/churn/evaluate?session_id=${sessionId}`);
}

export function getProducts(sessionId) {
  return request(`/api/products?session_id=${sessionId}`);
}

export function getRecommendations(sessionId, productId, method = "fpgrowth", topN = 5) {
  const params = new URLSearchParams({
    session_id: sessionId,
    product_id: String(productId),
    method,
    top_n: String(topN),
  });
  return request(`/api/recommendations?${params}`);
}

export function searchWindows(sessionId) {
  return request(`/api/windows/search?session_id=${sessionId}`);
}
