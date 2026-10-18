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
  status: () => request("GET", "/screen/api/status"),
  settings: () => request("GET", "/screen/api/settings"),
  updateSettings: (patch) => request("PUT", "/screen/api/settings", { body: patch }),
  pause: () => request("POST", "/screen/api/pause"),
  resume: () => request("POST", "/screen/api/resume"),
  setPrivate: (value) => request("POST", "/screen/api/private", { body: { private: value } }),
  exclusions: () => request("GET", "/screen/api/exclusions"),
  addExclusion: (kind, pattern) => request("POST", "/screen/api/exclusions", { body: { kind, pattern } }),
  toggleExclusion: (id, enabled) => request("PATCH", `/screen/api/exclusions/${id}`, { body: { enabled } }),
  removeExclusion: (id) => request("DELETE", `/screen/api/exclusions/${id}`),
  testExclusion: (app, title) => request("POST", "/screen/api/exclusions/test", { body: { app, title } }),
  timeline: (params) => request("GET", "/screen/api/timeline", { params }),
  sessions: (params) => request("GET", "/screen/api/sessions", { params }),
  frame: (id) => request("GET", `/screen/api/frames/${id}`),
  pinFrame: (id, pinned) => request("PATCH", `/screen/api/frames/${id}/pin`, { body: { pinned } }),
  search: (params) => request("GET", "/screen/api/search", { params }),
  similar: (id, params) => request("GET", `/screen/api/frames/${id}/similar`, { params }),
  visualStatus: () => request("GET", "/screen/api/visual"),
  visualDownload: () => request("POST", "/screen/api/visual/download"),
  visualReindex: () => request("POST", "/screen/api/visual/reindex"),
  apps: (params) => request("GET", "/screen/api/apps", { params }),
  days: () => request("GET", "/screen/api/days"),
  deleteRange: (from, to) => request("DELETE", "/screen/api/frames", { params: { from, to } }),
  imageUrl: (id) => `/screen/api/frames/${id}/image`,
  thumbUrl: (id) => `/screen/api/frames/${id}/thumb`,
};
