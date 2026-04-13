export { default } from "./PlatformApp";

/*
import { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const starterPrompts = [
  "Find 10 drug-like molecules for diabetes",
  'Score "CCO"',
  "Show the best molecules",
  "Open the latest report",
];

function formatValue(value) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}
*/

function formatConversationDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function normalizeAssistantMessage(payload) {
  return {
    role: payload?.message?.role || "assistant",
    content: payload?.message?.content || "No response returned.",
    type: payload?.message?.type || "text",
    tool_used: payload?.tool_used || null,
    data: payload?.data || null,
    created_at: payload?.created_at || new Date().toISOString(),
  };
}

function DataTable({ molecules = [] }) {
  if (!molecules.length) return null;

  return (
    <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white">
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-100 text-slate-700">
            <tr>
              <th className="px-4 py-3">Rank</th>
              <th className="px-4 py-3">SMILES</th>
              <th className="px-4 py-3">Clinical</th>
              <th className="px-4 py-3">QED</th>
              <th className="px-4 py-3">Recommendation</th>
            </tr>
          </thead>
          <tbody>
            {molecules.map((molecule, index) => (
              <tr key={`${molecule.smiles}-${index}`} className="border-t border-slate-100">
                <td className="px-4 py-3">{formatValue(molecule.rank ?? index + 1)}</td>
                <td className="max-w-sm px-4 py-3 font-mono text-xs text-slate-700">
                  {formatValue(molecule.smiles)}
                </td>
                <td className="px-4 py-3">{formatValue(molecule.clinical_score)}</td>
                <td className="px-4 py-3">{formatValue(molecule.qed_score)}</td>
                <td className="px-4 py-3">{formatValue(molecule.recommendation)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ScoreCard({ data }) {
  const fields = [
    ["SMILES", data.smiles],
    ["Clinical Score", data.clinical_score],
    ["QED Score", data.qed_score],
    ["SA Score", data.sa_score],
    ["Lipinski Pass", data.passes_lipinski],
    ["Recommendation", data.recommendation],
  ];

  return (
    <div className="mt-4 grid gap-3 rounded-2xl border border-emerald-200 bg-white p-4 sm:grid-cols-2">
      {fields.map(([label, value]) => (
        <div key={label} className="rounded-xl bg-slate-50 p-3">
          <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
          <div className="mt-1 break-all text-sm font-semibold text-slate-900">
            {formatValue(value)}
          </div>
        </div>
      ))}
    </div>
  );
}

function ReportCard({ data }) {
  const href = `${API_BASE_URL}${data.url}`;
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="mt-4 inline-flex rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800"
    >
      Open Report
    </a>
  );
}

function ErrorCard({ data }) {
  return (
    <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      {data?.detail || "Something went wrong."}
    </div>
  );
}

function AssistantContent({ message }) {
  const molecules = useMemo(() => {
    if (!message.data) return [];
    if (Array.isArray(message.data.molecules)) return message.data.molecules;
    return [];
  }, [message.data]);

  return (
    <>
      <div className="prose prose-sm max-w-none whitespace-pre-wrap prose-headings:mb-2 prose-p:my-2 prose-code:rounded prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:text-slate-800">
        <ReactMarkdown>{message.content}</ReactMarkdown>
      </div>
      {message.type === "table" ? <DataTable molecules={molecules} /> : null}
      {message.type === "score" ? <ScoreCard data={message.data || {}} /> : null}
      {message.type === "report" ? <ReportCard data={message.data || {}} /> : null}
      {message.type === "error" ? <ErrorCard data={message.data || {}} /> : null}
    </>
  );
}

function MessageBubble({ message }) {
  if (message.role === "user") {
    return (
      <div className="ml-auto max-w-3xl rounded-[28px] bg-slate-900 px-5 py-4 text-sm text-white shadow-sm">
        <div className="whitespace-pre-wrap">{message.content}</div>
      </div>
    );
  }

  return (
    <div className="mr-auto w-full max-w-3xl rounded-[28px] border border-slate-200 bg-white px-5 py-4 text-slate-900 shadow-sm">
      <AssistantContent message={message} />
    </div>
  );
}

function EmptyState({ onPromptClick }) {
  return (
    <div className="mx-auto flex max-w-3xl flex-1 flex-col items-center justify-center px-6 text-center">
      <div className="rounded-full border border-slate-200 bg-white px-4 py-2 text-xs font-semibold uppercase tracking-[0.25em] text-slate-500 shadow-sm">
        Genorova AI
      </div>
      <h1 className="mt-6 text-4xl font-semibold tracking-tight text-slate-900">
        Chemistry chat, wrapped like a product.
      </h1>
      <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600">
        Ask Genorova to generate candidates, score a molecule, inspect ranked results, or open the latest scientific report.
      </p>
      <div className="mt-10 grid w-full max-w-3xl gap-3 sm:grid-cols-2">
        {starterPrompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => onPromptClick(prompt)}
            className="rounded-2xl border border-slate-200 bg-white px-4 py-4 text-left text-sm text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function App() {
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pageError, setPageError] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function loadConversations(selectLatest = true) {
    try {
      setPageError("");
      const response = await fetch(`${API_BASE_URL}/conversations`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to load conversations.");
      }

      const nextConversations = payload.conversations || [];
      setConversations(nextConversations);

      if (selectLatest && nextConversations.length && !activeConversationId) {
        openConversation(nextConversations[0].id);
      }
    } catch (error) {
      setPageError(error.message);
    }
  }

  async function openConversation(conversationId) {
    if (!conversationId) return;

    try {
      setPageError("");
      const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}`);
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to open conversation.");
      }

      setActiveConversationId(payload.id);
      setMessages(payload.messages || []);
    } catch (error) {
      setPageError(error.message);
    }
  }

  async function createConversation() {
    try {
      setPageError("");
      const response = await fetch(`${API_BASE_URL}/conversations/new`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Unable to create conversation.");
      }

      const conversation = payload.conversation;
      setConversations((current) => [conversation, ...current.filter((item) => item.id !== conversation.id)]);
      setActiveConversationId(conversation.id);
      setMessages([]);
      setInput("");
      return conversation.id;
    } catch (error) {
      setPageError(error.message);
      return null;
    }
  }

  async function refreshConversationList() {
    try {
      const response = await fetch(`${API_BASE_URL}/conversations`);
      const payload = await response.json();
      if (response.ok) {
        setConversations(payload.conversations || []);
      }
    } catch {
      // Sidebar freshness is helpful but not critical to the main chat flow.
    }
  }

  async function sendMessage(text) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    let conversationId = activeConversationId;
    if (!conversationId) {
      conversationId = await createConversation();
      if (!conversationId) return;
    }

    const nextUserMessage = {
      role: "user",
      content: trimmed,
      type: "text",
      created_at: new Date().toISOString(),
    };

    setMessages((current) => [...current, nextUserMessage]);
    setInput("");
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: trimmed,
          conversation_id: conversationId,
        }),
      });

      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.detail || "Chat request failed.");
      }

      setActiveConversationId(payload.conversation_id);
      setMessages((current) => [...current, normalizeAssistantMessage(payload)]);
      await refreshConversationList();
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: "Request failed.\n\nPlease try again.",
          type: "error",
          data: { detail: error.message },
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    sendMessage(input);
  }

  function handleComposerKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit(event);
    }
  }

  const hasMessages = messages.length > 0;

  return (
    <div className="flex min-h-screen bg-slate-100 text-slate-900">
      <aside className="flex w-full max-w-[320px] flex-col border-r border-slate-800 bg-slate-950 text-slate-100">
        <div className="border-b border-slate-800 p-4">
          <div className="text-xs font-semibold uppercase tracking-[0.28em] text-slate-400">
            Genorova AI
          </div>
          <button
            type="button"
            onClick={createConversation}
            className="mt-4 w-full rounded-2xl bg-slate-800 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-700"
          >
            New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          <div className="px-2 pb-2 text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
            Conversations
          </div>

          {!conversations.length ? (
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-4 text-sm text-slate-400">
              No chats yet. Start a new conversation to begin.
            </div>
          ) : (
            <div className="space-y-2">
              {conversations.map((conversation) => {
                const isActive = conversation.id === activeConversationId;
                return (
                  <button
                    key={conversation.id}
                    type="button"
                    onClick={() => openConversation(conversation.id)}
                    className={`w-full rounded-2xl px-4 py-3 text-left transition ${
                      isActive
                        ? "bg-slate-800 text-white"
                        : "bg-transparent text-slate-300 hover:bg-slate-900 hover:text-white"
                    }`}
                  >
                    <div className="truncate text-sm font-medium">{conversation.title || "New Chat"}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {formatConversationDate(conversation.updated_at)}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </aside>

      <main className="flex min-h-screen flex-1 flex-col">
        <header className="border-b border-slate-200 bg-white px-6 py-4">
          <div className="mx-auto flex w-full max-w-5xl items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-slate-900">
                {conversations.find((item) => item.id === activeConversationId)?.title || "Genorova Chat"}
              </div>
              <div className="text-xs text-slate-500">
                Generate, score, and inspect molecules in a product-style workspace.
              </div>
            </div>
            <a
              href={`${API_BASE_URL}/docs`}
              target="_blank"
              rel="noreferrer"
              className="rounded-full border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
            >
              API Docs
            </a>
          </div>
        </header>

        <section className="flex flex-1 flex-col overflow-hidden">
          {pageError ? (
            <div className="mx-auto mt-6 w-full max-w-5xl rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {pageError}
            </div>
          ) : null}

          {!hasMessages && !loading ? (
            <EmptyState onPromptClick={sendMessage} />
          ) : (
            <div className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-4 overflow-y-auto px-4 py-6 sm:px-6">
              {messages.map((message, index) => (
                <div
                  key={`${message.role}-${message.created_at || index}-${index}`}
                  className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <MessageBubble message={message} />
                </div>
              ))}

              {loading ? (
                <div className="flex justify-start">
                  <div className="rounded-[28px] border border-slate-200 bg-white px-5 py-4 text-sm text-slate-500 shadow-sm">
                    Thinking through the Genorova pipeline...
                  </div>
                </div>
              ) : null}
              <div ref={bottomRef} />
            </div>
          )}
        </section>

        <footer className="border-t border-slate-200 bg-white px-4 py-4 sm:px-6">
          <form onSubmit={handleSubmit} className="mx-auto flex w-full max-w-5xl gap-3">
            <textarea
              rows={2}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder='Ask something like: Find 10 drug-like molecules for diabetes'
              className="min-h-[64px] flex-1 resize-none rounded-[28px] border border-slate-300 bg-slate-50 px-5 py-4 text-sm text-slate-900 outline-none transition focus:border-slate-400 focus:bg-white"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="rounded-[28px] bg-slate-900 px-6 py-4 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
            >
              Send
            </button>
          </form>
        </footer>
      </main>
    </div>
  );
}
