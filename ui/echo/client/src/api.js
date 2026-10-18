// Thin fetch wrapper: JSON in/out, `{ error }` bodies become exceptions.
async function request(method, path, { params, body } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }
  const response = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { error: text };
  }
  if (!response.ok) throw new Error((data && data.error) || `Error ${response.status}`);
  return data;
}

export const api = {
  health: () => request("GET", "/clipboard/api/health"),
  status: () => request("GET", "/clipboard/api/status"),
  pause: () => request("POST", "/clipboard/api/pause"),
  resume: () => request("POST", "/clipboard/api/resume"),

  clips: (params) => request("GET", "/clipboard/api/clips", { params }),
  clip: (id) => request("GET", `/clipboard/api/clips/${id}`),
  addClip: (text) => request("POST", "/clipboard/api/clips", { body: { text } }),
  updateClip: (id, patch) => request("PATCH", `/clipboard/api/clips/${id}`, { body: patch }),
  removeClip: (id) => request("DELETE", `/clipboard/api/clips/${id}`),
  restoreClip: (id) => request("POST", `/clipboard/api/clips/${id}/restore`),
  copyClip: (id) => request("POST", `/clipboard/api/clips/${id}/copy`),
  purgeBefore: (isoDate) => request("DELETE", "/clipboard/api/clips", { params: { before: isoDate } }),
  imageUrl: (id) => `/clipboard/api/clips/${id}/image`,

  search: (params) => request("GET", "/clipboard/api/search", { params }),
};
