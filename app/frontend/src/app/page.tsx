"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  streamChat,
  addRepository,
  listRepositories,
  getRulebook,
  regenerateRulebook,
  deleteRepository,
  getFindings,
  getWorkspace,
  clearSession,
  getWorkspaceId,
  isAuthenticated,
} from "@/lib/api";

type Repository = {
  id: string;
  name: string;
  owner: string;
  branch: string;
  status: string;
};

type RuleBookFile = {
  id: string;
  filename: string;
  content: string;
  version: number;
  generated_at: string;
};

type Finding = {
  id: string;
  event_type: string;
  external_id: string;
  severity: string;
  title: string;
  details: {
    pr_number?: number;
    title?: string;
    linked_issue?: number;
    explanation?: string;
  };
  checked_at: string;
};

export default function Dashboard() {
  const router = useRouter();

  // Auth + workspace
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [workspaceName, setWorkspaceName] = useState("Your workspace");

  // Repositories
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rulebooks, setRulebooks] = useState<RuleBookFile[]>([]);
  const [selectedRulebookTab, setSelectedRulebookTab] = useState<string>("CLAUDE.md");
  const [findings, setFindings] = useState<Finding[]>([]);
  
  // Loading states
  const [rulebooksLoading, setRulebooksLoading] = useState(false);
  const [findingsLoading, setFindingsLoading] = useState(false);
  const [rulebooksNotReady, setRulebooksNotReady] = useState(false);

  // Add Repository Form
  const [repoName, setRepoName] = useState("");
  const [repoOwner, setRepoOwner] = useState("");
  const [repoBranch, setRepoBranch] = useState("main");
  const [addStatus, setAddStatus] = useState("");
  const [showAddForm, setShowAddForm] = useState(false);

  // Chat
  const [query, setQuery] = useState("");
  const [chatMessages, setChatMessages] = useState<{ role: "user" | "assistant"; text: string }[]>([]);
  const [chatLoading, setChatLoading] = useState(false);

  // Views: 'rulebook' | 'findings' | 'chat'
  const [activeView, setActiveView] = useState<"rulebook" | "findings" | "chat">("rulebook");

  // ── Auth gate ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    const wid = getWorkspaceId()!;
    setWorkspaceId(wid);
    loadWorkspace(wid);
    loadRepositories(wid);
  }, []);

  async function loadWorkspace(wid: string) {
    const data = await getWorkspace(wid);
    if (data?.name) setWorkspaceName(data.name);
  }

  async function loadRepositories(wid: string) {
    const data = await listRepositories(wid);
    if (Array.isArray(data)) {
      setRepositories(data);
      if (data.length > 0 && !selectedId) {
        selectRepository(data[0].id, data);
      }
    }
  }

  // ── Select repository → load context ──────────────────────────────────
  async function selectRepository(repoId: string, repoList: Repository[] = repositories) {
    setSelectedId(repoId);
    
    // Reset states
    setRulebooks([]);
    setRulebooksNotReady(false);
    setRulebooksLoading(true);
    setFindingsLoading(true);
    setFindings([]);

    // Load Rulebook
    const rbData = await getRulebook(workspaceId!, repoId);
    setRulebooksLoading(false);
    if (Array.isArray(rbData) && rbData.length > 0) {
      setRulebooks(rbData);
      const firstTab = rbData[0]?.filename || "CLAUDE.md";
      setSelectedRulebookTab(firstTab);
    } else {
      setRulebooksNotReady(true);
    }

    // Load Webhook Findings
    const findingsData = await getFindings(workspaceId!, repoId);
    setFindingsLoading(false);
    if (Array.isArray(findingsData)) {
      setFindings(findingsData);
    }
  }

  // ── Add Repository ─────────────────────────────────────────────────────────
  async function handleAddRepository(e: React.FormEvent) {
    e.preventDefault();
    if (!repoName || !repoOwner || !workspaceId) return;
    setAddStatus("Initializing indexing...");
    const result = await addRepository(workspaceId, repoName, repoOwner, repoBranch);
    if (result.id) {
      const newRepo = { 
        id: result.id, 
        name: repoName, 
        owner: repoOwner, 
        branch: repoBranch, 
        status: "indexing" 
      };
      setRepositories((prev) => [...prev, newRepo]);
      setAddStatus(`Indexing started for ${repoOwner}/${repoName}. Compiled rules ready in ~1 min.`);
      setRepoName("");
      setRepoOwner("");
      setRepoBranch("main");
      setShowAddForm(false);
      selectRepository(result.id, [...repositories, newRepo]);
    } else {
      setAddStatus("Error adding repository.");
    }
  }

  // ── Delete Repository ──────────────────────────────────────────────────────
  async function handleDelete(id: string) {
    if (!workspaceId) return;
    await deleteRepository(workspaceId, id);
    setRepositories((prev) => prev.filter((r) => r.id !== id));
    if (selectedId === id) {
      setSelectedId(null);
      setRulebooks([]);
      setFindings([]);
    }
  }

  // ── Regenerate rulebook ─────────────────────────────────────────────────
  async function handleRegenerate() {
    if (!selectedId || !workspaceId) return;
    setRulebooksNotReady(true);
    setRulebooks([]);
    setAddStatus("Regeneration started. Updating in ~1 minute.");
    await regenerateRulebook(workspaceId, selectedId);
    
    // Simulate updating state by loading repos again
    setTimeout(() => {
      if (selectedId) selectRepository(selectedId);
      setAddStatus("");
    }, 5000);
  }

  // ── Chat ───────────────────────────────────────────────────────────────────
  async function handleChat(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim() || !workspaceId) return;
    const userMsg = query.trim();
    setQuery("");
    setChatMessages((prev) => [...prev, { role: "user", text: userMsg }]);
    setChatLoading(true);
    setActiveView("chat");

    let assistantText = "";
    setChatMessages((prev) => [...prev, { role: "assistant", text: "" }]);

    try {
      for await (const chunk of streamChat(workspaceId, userMsg)) {
        assistantText += chunk;
        setChatMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = { role: "assistant", text: assistantText };
          return updated;
        });
      }
    } catch (err) {
      setChatMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", text: `Error: ${err instanceof Error ? err.message : "Could not reach server."}` };
        return updated;
      });
    }
    setChatLoading(false);
  }

  function handleLogout() {
    clearSession();
    router.push("/login");
  }

  const selectedRepo = repositories.find((r) => r.id === selectedId);

  return (
    <div className="min-h-screen flex bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500/30 selection:text-indigo-200">
      {/* Side Navigation Panel */}
      <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col flex-shrink-0">
        <div className="p-6 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <div className="w-3.5 h-3.5 rounded-full bg-indigo-500 shadow-[0_0_12px_rgba(99,102,241,0.5)] animate-pulse" />
            <h1 className="text-base font-bold text-white tracking-tight">Groundtruth</h1>
          </div>
          <p className="text-xs text-slate-500 mt-1 truncate">{workspaceName}</p>
        </div>

        <nav className="flex-1 p-4 flex flex-col gap-1 text-sm">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2 px-3">
            Company Brain
          </div>
          <button
            onClick={() => setActiveView("rulebook")}
            className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all flex items-center justify-between ${
              activeView === "rulebook"
                ? "bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 shadow-[0_2px_8px_rgba(99,102,241,0.05)]"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent"
            }`}
          >
            <span>Compiled Rules</span>
            <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-md font-mono">CLAUDE.md</span>
          </button>
          
          <button
            onClick={() => setActiveView("findings")}
            className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all flex items-center justify-between ${
              activeView === "findings"
                ? "bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 shadow-[0_2px_8px_rgba(99,102,241,0.05)]"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent"
            }`}
          >
            <span>Live Findings</span>
            {findings.length > 0 && (
              <span className="w-2 h-2 rounded-full bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)] animate-pulse" />
            )}
          </button>

          <button
            onClick={() => setActiveView("chat")}
            className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all flex items-center justify-between ${
              activeView === "chat"
                ? "bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 shadow-[0_2px_8px_rgba(99,102,241,0.05)]"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 border border-transparent"
            }`}
          >
            <span>Query Brain</span>
            <span className="text-[10px] bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded-md">Ask AI</span>
          </button>
        </nav>

        <div className="p-4 border-t border-slate-800">
          <button
            onClick={handleLogout}
            className="w-full text-left px-3 py-2 text-xs text-slate-500 hover:text-slate-300 rounded-lg hover:bg-slate-800/50 transition-colors"
          >
            Sign out
          </button>
        </div>
      </aside>

      {/* Connected Repositories Panel */}
      <div className="w-72 bg-slate-900/60 border-r border-slate-800/80 flex flex-col flex-shrink-0 backdrop-blur-md">
        <div className="px-5 py-5 border-b border-slate-800 flex items-center justify-between">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Repositories</span>
          <button
            onClick={() => setShowAddForm((v) => !v)}
            className="text-xs text-indigo-400 hover:text-indigo-300 font-medium px-2 py-1 rounded hover:bg-indigo-500/5 transition-all"
          >
            + Add Repo
          </button>
        </div>

        {/* Add repo form */}
        {showAddForm && (
          <form onSubmit={handleAddRepository} className="p-4 border-b border-slate-800/80 flex flex-col gap-3 bg-slate-900/40">
            <div>
              <label className="text-[10px] text-slate-400 uppercase tracking-wider block mb-1">Owner</label>
              <input
                className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500/50 transition-all font-mono"
                placeholder="e.g. mem0ai"
                value={repoOwner}
                onChange={(e) => setRepoOwner(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400 uppercase tracking-wider block mb-1">Repo Name</label>
              <input
                className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500/50 transition-all font-mono"
                placeholder="e.g. mem0"
                value={repoName}
                onChange={(e) => setRepoName(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400 uppercase tracking-wider block mb-1">Default Branch</label>
              <input
                className="w-full bg-slate-950 border border-slate-800 rounded-md px-3 py-2 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500/50 transition-all font-mono"
                placeholder="main"
                value={repoBranch}
                onChange={(e) => setRepoBranch(e.target.value)}
              />
            </div>
            <button
              type="submit"
              className="w-full bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold py-2 rounded-md transition-all shadow-[0_2px_8px_rgba(99,102,241,0.2)] hover:shadow-[0_2px_12px_rgba(99,102,241,0.3)]"
            >
              Analyze & Index
            </button>
            {addStatus && <p className="text-[10px] text-indigo-300 font-mono mt-1">{addStatus}</p>}
          </form>
        )}

        {/* Repos list */}
        <div className="flex-1 overflow-auto p-3 flex flex-col gap-1.5">
          {repositories.length === 0 ? (
            <div className="text-center py-12 px-4">
              <p className="text-xs text-slate-500">No repositories added yet.</p>
              <p className="text-[11px] text-slate-600 mt-2">Add a repository to begin compiling rules and tracking drift.</p>
            </div>
          ) : (
            repositories.map((repo) => (
              <div
                key={repo.id}
                onClick={() => selectRepository(repo.id)}
                className={`group flex items-center justify-between p-3.5 rounded-lg cursor-pointer transition-all border ${
                  selectedId === repo.id
                    ? "bg-slate-800/80 border-slate-700/60 shadow-lg text-white"
                    : "hover:bg-slate-800/40 border-transparent text-slate-400 hover:text-slate-200"
                }`}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <p className="text-xs font-mono truncate">{repo.owner} / <span className="font-bold text-white">{repo.name}</span></p>
                  </div>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-[10px] font-mono text-slate-500">{repo.branch}</span>
                    <span className="w-1 h-1 rounded-full bg-slate-600" />
                    <span className={`text-[10px] font-mono capitalize ${
                      repo.status === "active" ? "text-emerald-400" : "text-indigo-400 animate-pulse"
                    }`}>
                      {repo.status}
                    </span>
                  </div>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(repo.id); }}
                  className="opacity-0 group-hover:opacity-100 text-slate-600 hover:text-red-400 text-xs ml-2 transition-all p-1 hover:bg-slate-800 rounded"
                >
                  ✕
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main Workspace Workspace */}
      <main className="flex-1 flex flex-col min-w-0 bg-slate-950">
        {/* Header */}
        <header className="border-b border-slate-900 px-8 py-5 flex items-center justify-between flex-shrink-0 bg-slate-900/10 backdrop-blur-md z-10">
          <div className="flex items-center gap-3">
            {selectedRepo ? (
              <>
                <h2 className="text-sm font-semibold text-white font-mono">
                  {selectedRepo.owner} / <span className="font-bold">{selectedRepo.name}</span>
                </h2>
                <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded font-mono font-bold ${
                  selectedRepo.status === "active" ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 animate-pulse"
                }`}>
                  {selectedRepo.status}
                </span>
              </>
            ) : (
              <h2 className="text-sm font-semibold text-slate-400">Select a repository to begin</h2>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveView("rulebook")}
              disabled={!selectedId}
              className={`text-xs px-3.5 py-2 rounded-lg font-medium transition-all ${
                activeView === "rulebook" && selectedId
                  ? "bg-slate-800 text-white border border-slate-700 shadow-md"
                  : "text-slate-400 hover:text-slate-200 border border-transparent disabled:opacity-30 disabled:cursor-not-allowed"
              }`}
            >
              Rulebook
            </button>
            <button
              onClick={() => setActiveView("findings")}
              disabled={!selectedId}
              className={`text-xs px-3.5 py-2 rounded-lg font-medium transition-all relative ${
                activeView === "findings" && selectedId
                  ? "bg-slate-800 text-white border border-slate-700 shadow-md"
                  : "text-slate-400 hover:text-slate-200 border border-transparent disabled:opacity-30 disabled:cursor-not-allowed"
              }`}
            >
              Findings
              {findings.length > 0 && selectedId && (
                <span className="absolute -top-1 -right-1 w-2.5 h-2.5 rounded-full bg-amber-500 border-2 border-slate-950" />
              )}
            </button>
            <button
              onClick={() => setActiveView("chat")}
              disabled={!selectedId}
              className={`text-xs px-3.5 py-2 rounded-lg font-medium transition-all ${
                activeView === "chat" && selectedId
                  ? "bg-slate-800 text-white border border-slate-700 shadow-md"
                  : "text-slate-400 hover:text-slate-200 border border-transparent disabled:opacity-30 disabled:cursor-not-allowed"
              }`}
            >
              Chat
            </button>
          </div>
        </header>

        {/* Content Body */}
        <div className="flex-1 overflow-auto p-8 bg-gradient-to-br from-slate-950 via-slate-950 to-indigo-950/20">
          
          {/* 1. Rulebooks view */}
          {activeView === "rulebook" && selectedId && (
            <div className="max-w-4xl mx-auto flex flex-col gap-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {rulebooks.map((rb) => (
                    <button
                      key={rb.id}
                      onClick={() => setSelectedRulebookTab(rb.filename)}
                      className={`text-xs font-mono font-bold px-3 py-1.5 rounded-md border transition-all ${
                        selectedRulebookTab === rb.filename
                          ? "bg-indigo-500/10 text-indigo-400 border-indigo-500/30"
                          : "bg-slate-900/40 text-slate-400 border-slate-800 hover:text-slate-200"
                      }`}
                    >
                      {rb.filename}
                    </button>
                  ))}
                </div>
                <button
                  onClick={handleRegenerate}
                  className="text-xs font-medium text-slate-400 hover:text-indigo-400 transition-colors flex items-center gap-1.5"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3 3 3m-3-3v12" />
                  </svg>
                  Compile Rules
                </button>
              </div>

              {rulebooksLoading && (
                <div className="bg-slate-900/40 border border-slate-900 rounded-xl p-12 text-center backdrop-blur-sm">
                  <p className="text-sm text-slate-400 animate-pulse font-mono">Indexing repo structure and compiling rules...</p>
                </div>
              )}

              {rulebooksNotReady && !rulebooksLoading && (
                <div className="bg-slate-900/40 border border-slate-900 rounded-xl p-12 text-center backdrop-blur-sm">
                  <p className="text-sm text-slate-400">Rules under compilation.</p>
                  <p className="text-xs text-slate-600 mt-1 font-mono">Scanning recent commits and issues to compile guidelines. Ready in ~1 minute.</p>
                </div>
              )}

              {rulebooks.map((rb) => {
                if (rb.filename !== selectedRulebookTab) return null;
                return (
                  <div key={rb.id} className="flex flex-col gap-3">
                    <div className="bg-slate-900/60 rounded-xl border border-slate-800/80 p-7 shadow-xl backdrop-blur-sm relative overflow-hidden">
                      <div className="absolute top-0 right-0 p-3 text-[10px] font-mono text-slate-600 bg-slate-900/80 border-b border-l border-slate-800 rounded-bl-lg">
                        v{rb.version.toFixed(1)}
                      </div>
                      <pre className="text-xs font-mono text-slate-300 whitespace-pre-wrap leading-relaxed">
                        {rb.content}
                      </pre>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-600 font-mono px-1">
                      <span>File: {rb.filename}</span>
                      <span>Last compiled: {new Date(rb.generated_at).toLocaleString()}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* 2. Webhook Findings view */}
          {activeView === "findings" && selectedId && (
            <div className="max-w-4xl mx-auto flex flex-col gap-5">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <h3 className="text-sm font-semibold text-white">Live Policy Checks</h3>
                  <p className="text-xs text-slate-500 mt-0.5">Real-time alerts triggered by developer actions compared with compiled rules.</p>
                </div>
                <span className="text-xs font-mono bg-slate-900 text-slate-400 px-3 py-1 rounded-md border border-slate-800">
                  {findings.length} findings
                </span>
              </div>

              {findingsLoading && (
                <div className="bg-slate-900/40 border border-slate-900 rounded-xl p-12 text-center backdrop-blur-sm">
                  <p className="text-sm text-slate-400 animate-pulse font-mono font-bold">Scanning webhook logs...</p>
                </div>
              )}

              {!findingsLoading && findings.length === 0 && (
                <div className="bg-slate-900/40 border border-slate-900 rounded-xl p-12 text-center backdrop-blur-sm border-dashed">
                  <svg className="w-8 h-8 text-slate-700 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <p className="text-sm text-slate-400">All checks passing. No discrepancies found.</p>
                  <p className="text-xs text-slate-600 mt-1">Webhook listener is active. Push new commits or PRs to trigger checks.</p>
                </div>
              )}

              {findings.map((finding) => (
                <div
                  key={finding.id}
                  className="bg-slate-900/40 border border-slate-900 rounded-xl p-6 hover:bg-slate-900/60 transition-all flex flex-col gap-4 backdrop-blur-sm"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                        finding.severity === "error" 
                          ? "bg-rose-500/10 text-rose-400 border border-rose-500/20" 
                          : finding.severity === "warning" 
                          ? "bg-amber-500/10 text-amber-400 border border-amber-500/20" 
                          : "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20"
                      }`}>
                        {finding.severity}
                      </span>
                      <h4 className="text-xs font-semibold text-white">{finding.title}</h4>
                    </div>
                    <span className="text-[10px] font-mono text-slate-600">
                      {new Date(finding.checked_at).toLocaleTimeString()}
                    </span>
                  </div>

                  {finding.details && (
                    <div className="bg-slate-950/80 rounded-lg p-4 border border-slate-900 font-mono text-[11px] leading-relaxed text-slate-400">
                      <div className="flex justify-between border-b border-slate-900 pb-2 mb-2">
                        <span>Event: {finding.event_type.toUpperCase()}</span>
                        <span className="text-indigo-400">PR #{finding.details.pr_number}</span>
                      </div>
                      <p className="text-white mb-2">{finding.details.title}</p>
                      <p className="text-slate-500">{finding.details.explanation}</p>
                    </div>
                  )}

                  <div className="flex items-center justify-between text-[10px] font-mono text-slate-500">
                    <span>Target: issue #{finding.details?.linked_issue}</span>
                    <span>Webhook check: OK</span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* 3. Interactive Chat view */}
          {activeView === "chat" && (
            <div className="max-w-4xl mx-auto flex flex-col h-full" style={{ minHeight: "65vh" }}>
              <div className="flex-1 flex flex-col gap-4 mb-6 overflow-auto pr-2">
                {chatMessages.length === 0 && (
                  <div className="text-center py-16">
                    <svg className="w-10 h-10 text-slate-800 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                    </svg>
                    <p className="text-sm text-slate-400">Ask Groundtruth about repository rules and standards.</p>
                    <p className="text-xs text-slate-600 mt-1 font-mono">
                      Try: "What are the linting conventions for this project?" or "Where should I add new agents?"
                    </p>
                  </div>
                )}
                {chatMessages.map((msg, i) => (
                  <div
                    key={i}
                    className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-2xl rounded-xl px-5 py-3 text-xs leading-relaxed border ${
                        msg.role === "user"
                          ? "bg-indigo-600 border-indigo-500 text-white shadow-lg shadow-indigo-600/10"
                          : "bg-slate-900/60 border-slate-900 text-slate-200 backdrop-blur-sm"
                      }`}
                    >
                      <pre className="whitespace-pre-wrap font-mono leading-relaxed">{msg.text}</pre>
                    </div>
                  </div>
                ))}
              </div>

              <form onSubmit={handleChat} className="flex gap-2.5 mt-auto">
                <input
                  className="flex-1 bg-slate-900/80 border border-slate-800 rounded-xl px-4 py-3 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500/50 transition-all font-mono"
                  placeholder="Ask your company brain..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <button
                  type="submit"
                  disabled={chatLoading}
                  className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold px-6 rounded-xl transition-all shadow-[0_2px_8px_rgba(99,102,241,0.2)] hover:shadow-[0_2px_12px_rgba(99,102,241,0.3)] flex items-center justify-center min-w-[70px]"
                >
                  {chatLoading ? (
                    <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    "Query"
                  )}
                </button>
              </form>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
