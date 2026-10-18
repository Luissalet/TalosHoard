// Thin fetch wrapper: JSON in/out, `{ error }` bodies become exceptions.
async function request(method, path, { params, body, form } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, value);
  }
  const response = await fetch(url, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: form !== undefined ? form : body !== undefined ? JSON.stringify(body) : undefined,
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
  status: () => request("GET", "/audio/api/status"),
  devices: () => request("GET", "/audio/api/devices"),
  settings: () => request("GET", "/audio/api/settings"),
  updateSettings: (patch) => request("PUT", "/audio/api/settings", { body: patch }),
  downloadModel: () => request("POST", "/audio/api/models/download"),
  start: (body) => request("POST", "/audio/api/sessions/start", { body }),
  stop: (id) => request("POST", `/audio/api/sessions/${id}/stop`),
  sessions: (params) => request("GET", "/audio/api/sessions", { params }),
  session: (id) => request("GET", `/audio/api/sessions/${id}`),
  patchSession: (id, patch) => request("PATCH", `/audio/api/sessions/${id}`, { body: patch }),
  deleteSession: (id) => request("DELETE", `/audio/api/sessions/${id}`),
  retranscribe: (id) => request("POST", `/audio/api/sessions/${id}/retranscribe`),
  minutes: (id) => request("GET", `/audio/api/sessions/${id}/minutes`),
  makeMinutes: (id, body) => request("POST", `/audio/api/sessions/${id}/minutes`, { body }),
  minutesMarkdown: async (id) => {
    const response = await fetch(`/audio/api/sessions/${id}/minutes?format=md`);
    if (!response.ok) throw new Error(`Error ${response.status}`);
    return response.text();
  },
  peaks: (id, n = 400) => request("GET", `/audio/api/sessions/${id}/peaks`, { params: { n } }),
  search: (params) => request("GET", "/audio/api/search", { params }),
  tags: () => request("GET", "/audio/api/tags"),
  importFile: (file, fields) => {
    const form = new FormData();
    form.append("file", file, file.name);
    for (const [key, value] of Object.entries(fields || {})) form.append(key, value);
    return request("POST", "/audio/api/import", { form });
  },
  audioUrl: (id) => `/audio/api/sessions/${id}/audio`,
  exportUrl: (id, format) => `/audio/api/sessions/${id}/export?format=${format}`,
  liveUrl: (id) => `/audio/api/sessions/${id}/live`,
};
