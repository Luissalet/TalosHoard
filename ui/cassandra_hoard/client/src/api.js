// Thin fetch wrapper: JSON in/out, `{ error }` bodies become exceptions.
async function request(method, path, { params, body } = {}) {
  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "" && value !== false) url.searchParams.set(key, value);
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
  status: () => request("GET", "/services/api/status"),
  services: () => request("GET", "/services/api/services"),
  service: (id) => request("GET", `/services/api/services/${encodeURIComponent(id)}`),
  lanes: (hours = 24) => request("GET", "/services/api/lanes", { params: { hours } }),
  incidents: (params) => request("GET", "/services/api/incidents", { params }),
  incident: (id) => request("GET", `/services/api/incidents/${id}`),
  logs: (params) => request("GET", "/services/api/logs", { params }),
  logSources: () => request("GET", "/services/api/logs/sources"),
  gpu: (params) => request("GET", "/services/api/gpu", { params }),
  settings: () => request("GET", "/services/api/settings"),
  watch: (body) => request("POST", "/services/api/services", { body }),
  unwatch: (id) => request("DELETE", `/services/api/services/${encodeURIComponent(id)}`),
  policy: (id, body) => request("PUT", `/services/api/services/${encodeURIComponent(id)}/policy`, { body }),
  restart: (id) => request("POST", `/services/api/services/${encodeURIComponent(id)}/restart`),
  poll: () => request("POST", "/services/api/poll"),
  audit: (params) => request("GET", "/services/api/audit", { params }),
  auditStats: (params) => request("GET", "/services/api/audit/stats", { params }),
  auditSync: () => request("POST", "/services/api/audit/sync"),
  secrets: () => request("GET", "/services/api/secrets"),
  sites: (hours = 24) => request("GET", "/services/api/sites", { params: { hours } }),
  siteHistory: (id, params) => request("GET", `/services/api/sites/${encodeURIComponent(id)}/history`, { params }),
  watchSite: (body) => request("POST", "/services/api/sites", { body }),
  unwatchSite: (id) => request("DELETE", `/services/api/sites/${encodeURIComponent(id)}`),
  faustusFarm: () => request("GET", "/services/api/faustus/farm"),
  checkSites: (site) => request("POST", "/services/api/sites/check", { body: site ? { site } : {} }),
};
