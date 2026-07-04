const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Auth helpers ────────────────────────────────────────────────────────────

function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem("bb_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function saveSession(token: string, workspaceId: string) {
  localStorage.setItem("bb_token", token);
  localStorage.setItem("bb_workspace_id", workspaceId);
}

export function clearSession() {
  localStorage.removeItem("bb_token");
  localStorage.removeItem("bb_workspace_id");
}

export function getWorkspaceId(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("bb_workspace_id");
}

export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("bb_token");
}

// ── Auth API ─────────────────────────────────────────────────────────────────

export async function signup(email: string, password: string, companyName: string) {
  const res = await fetch(`${API_BASE}/api/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, company_name: companyName }),
  });
  return res.json();
}

export async function login(email: string, password: string) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return res.json();
}

// ── Workspace API ─────────────────────────────────────────────────────────────

export async function getWorkspace(workspaceId: string) {
  const res = await fetch(`${API_BASE}/api/workspaces/${workspaceId}`, {
    headers: authHeader(),
  });
  return res.json();
}

// ── Repositories API ───────────────────────────────────────────────────────────

export async function listRepositories(workspaceId: string) {
  const res = await fetch(`${API_BASE}/api/repositories/${workspaceId}`, {
    headers: authHeader(),
  });
  return res.json();
}

export async function addRepository(workspaceId: string, name: string, owner: string, branch: string = "main") {
  const res = await fetch(`${API_BASE}/api/repositories/${workspaceId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ name, owner, branch }),
  });
  return res.json();
}

export async function deleteRepository(workspaceId: string, repositoryId: string) {
  const res = await fetch(`${API_BASE}/api/repositories/${workspaceId}/${repositoryId}`, {
    method: "DELETE",
    headers: authHeader(),
  });
  return res.json();
}

export async function getRulebook(workspaceId: string, repositoryId: string) {
  const res = await fetch(
    `${API_BASE}/api/repositories/${workspaceId}/${repositoryId}/rulebook`,
    { headers: authHeader() }
  );
  if (!res.ok) return null;
  return res.json();
}

export async function regenerateRulebook(workspaceId: string, repositoryId: string) {
  const res = await fetch(
    `${API_BASE}/api/repositories/${workspaceId}/${repositoryId}/rulebook/regenerate`,
    { method: "POST", headers: authHeader() }
  );
  return res.json();
}

export async function getFindings(workspaceId: string, repositoryId: string) {
  const res = await fetch(
    `${API_BASE}/api/repositories/${workspaceId}/${repositoryId}/findings`,
    { headers: authHeader() }
  );
  return res.json();
}

// ── Chat API ──────────────────────────────────────────────────────────────────

export async function* streamChat(workspaceId: string, query: string): AsyncGenerator<string> {
  const res = await fetch(`${API_BASE}/api/chat/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ workspace_id: workspaceId, query }),
  });
  if (!res.ok || !res.body) return;
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value);
    for (const line of chunk.split("\n")) {
      if (line.startsWith("data: ") && line !== "data: [DONE]") {
        yield line.slice(6);
      }
    }
  }
}
