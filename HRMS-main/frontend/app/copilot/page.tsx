"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { Bot, LoaderCircle, MessageSquareText, Send, ShieldCheck, Sparkles, UserRound } from "lucide-react";
import { useRouter } from "next/navigation";

import { Sidebar } from "@/components/layout/sidebar";
import { Topbar } from "@/components/layout/topbar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { fetchProfile, sendCopilotMessage, type CopilotAgentResult, type CopilotHistoryMessage } from "@/lib/api";

type CopilotMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  result?: CopilotAgentResult | null;
};

const suggestions = [
  "What is the casual leave policy?",
  "Which employees know Python?",
  "How much leave do I have?",
  "Create an IT ticket for my laptop issue",
];

function makeId() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function errorMessage(body: unknown, fallback: string) {
  if (!body || typeof body !== "object") return fallback;
  const value = body as Record<string, unknown>;
  if (value.error && typeof value.error === "object") {
    const message = (value.error as Record<string, unknown>).message;
    if (typeof message === "string") return message;
  }
  const detail = value.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object") {
    const nested = detail as Record<string, unknown>;
    if (typeof nested.message === "string") return nested.message;
    if (nested.error && typeof nested.error === "object") {
      const message = (nested.error as Record<string, unknown>).message;
      if (typeof message === "string") return message;
    }
  }
  return fallback;
}

export default function CopilotPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [name, setName] = useState("User");
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<CopilotMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [authReady, setAuthReady] = useState(false);
  const endOfMessagesRef = useRef<HTMLDivElement | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);

  const clearAuthAndRedirect = useCallback(() => {
    localStorage.removeItem("hrms_access_token");
    document.cookie = "hrms_auth=; path=/; max-age=0; samesite=lax";
    document.cookie = "hrms_role=; path=/; max-age=0; samesite=lax";
    router.push("/login");
  }, [router]);

  useEffect(() => {
    const accessToken = localStorage.getItem("hrms_access_token");
    if (!accessToken) {
      clearAuthAndRedirect();
      return;
    }
    setToken(accessToken);
    setSessionId(makeId());
    setAuthReady(true);

    let cancelled = false;
    fetchProfile(accessToken).then((result) => {
      if (cancelled) return;
      if (result.status === 401 || result.status === 403) {
        clearAuthAndRedirect();
        return;
      }
      if (result.ok && "success" in result.body && result.body.success) {
        setName(result.body.data.name);
      }
    }).catch(() => {
      // Profile display is optional; the chat request reports API availability.
    });

    return () => {
      cancelled = true;
    };
  }, [clearAuthAndRedirect]);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const question = draft.trim();
    if (!question || sending) return;
    if (!token) {
      clearAuthAndRedirect();
      return;
    }

    const history: CopilotHistoryMessage[] = messages.slice(-8).map(({ role, content }) => ({ role, content }));
    setMessages((current) => [...current, { id: makeId(), role: "user", content: question }]);
    setDraft("");
    setError("");
    setSending(true);

    try {
      const response = await sendCopilotMessage(token, {
        question,
        session_id: sessionId || makeId(),
        history,
      });
      if (response.status === 401 || response.status === 403) {
        clearAuthAndRedirect();
        return;
      }
      if (!response.ok || !("success" in response.body) || !response.body.success) {
        setError(errorMessage(response.body, "HR Copilot could not complete that request. Please try again."));
        return;
      }

      const reply = response.body.data;
      setMessages((current) => [
        ...current,
        {
          id: makeId(),
          role: "assistant",
          content: reply.answer,
          result: reply.result,
        },
      ]);
    } catch {
      setError("Unable to reach HR Copilot. Check your connection and try again.");
    } finally {
      setSending(false);
    }
  };

  const onInputKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      formRef.current?.requestSubmit();
    }
  };

  return (
    <main className="flex min-h-screen">
      <Sidebar />
      <section className="flex min-w-0 flex-1 flex-col">
        <Topbar name={name} title="HR Copilot" />
        <div className="flex flex-1 flex-col p-4 md:p-7">
          <Card className="mx-auto flex min-h-[70vh] w-full max-w-5xl flex-1 flex-col overflow-hidden border-slate-200/80 bg-white/90 shadow-lg shadow-slate-900/5">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4 md:px-7">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-600 to-violet-500 text-white shadow-sm">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div>
                  <h2 className="font-semibold text-slate-900">Ask HR Copilot</h2>
                  <p className="text-xs text-slate-500">Policies, HR data, and everyday requests</p>
                </div>
              </div>
              <div className="hidden items-center gap-1.5 rounded-full bg-slate-50 px-3 py-1.5 text-xs text-slate-500 sm:flex">
                <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
                Authenticated workspace
              </div>
            </div>

            <CardContent className="flex min-h-0 flex-1 flex-col p-0">
              <div className="flex-1 space-y-5 overflow-y-auto px-4 py-5 md:px-7" aria-live="polite" aria-busy={sending}>
                {messages.length === 0 ? (
                  <div className="mx-auto flex min-h-[360px] max-w-2xl flex-col items-center justify-center text-center">
                    <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600">
                      <MessageSquareText className="h-7 w-7" />
                    </div>
                    <h3 className="text-xl font-semibold tracking-tight text-slate-900">How can I help?</h3>
                    <p className="mt-2 max-w-lg text-sm leading-6 text-slate-500">
                      Ask about an HR policy, explore approved HR data, or request an action. Your access is checked by the server.
                    </p>
                    <div className="mt-7 flex flex-wrap justify-center gap-2">
                      {suggestions.map((suggestion) => (
                        <button
                          className="rounded-full border border-slate-200 bg-white px-3.5 py-2 text-left text-xs text-slate-600 shadow-sm transition hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 disabled:opacity-50"
                          disabled={!authReady || sending}
                          key={suggestion}
                          onClick={() => setDraft(suggestion)}
                          type="button"
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  messages.map((message) => (
                    <article className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`} key={message.id}>
                      {message.role === "assistant" ? (
                        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-indigo-100 text-indigo-700">
                          <Bot className="h-4 w-4" />
                        </div>
                      ) : null}
                      <div className={`max-w-[88%] space-y-2 md:max-w-[78%] ${message.role === "user" ? "items-end" : "items-start"}`}>
                        <div className={message.role === "user"
                          ? "rounded-2xl rounded-tr-md bg-indigo-600 px-4 py-3 text-sm leading-6 text-white shadow-sm"
                          : "rounded-2xl rounded-tl-md border border-slate-200 bg-white px-4 py-3 text-sm leading-6 text-slate-800 shadow-sm"}>
                          <p className="whitespace-pre-wrap">{message.content}</p>
                        </div>
                        {message.role === "assistant" && message.result?.sources?.length ? (
                          <div className="w-full rounded-xl border border-emerald-100 bg-emerald-50/70 p-3">
                            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-emerald-800">Policy sources</p>
                            <div className="flex flex-wrap gap-2">
                              {message.result.sources.map((source, index) => (
                                <div className="rounded-lg border border-emerald-100 bg-white px-3 py-2 text-xs text-slate-700" key={`${source.policy}-${source.section}-${index}`}>
                                  <span className="font-medium">{source.policy}</span>
                                  {source.section ? <span className="text-slate-500"> · {source.section}</span> : null}
                                </div>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                      {message.role === "user" ? (
                        <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-slate-200 text-slate-700">
                          <UserRound className="h-4 w-4" />
                        </div>
                      ) : null}
                    </article>
                  ))
                )}
                {sending ? (
                  <div className="flex items-center gap-3 text-sm text-slate-500">
                    <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-indigo-100 text-indigo-700"><Bot className="h-4 w-4" /></div>
                    <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3">
                      <LoaderCircle className="h-4 w-4 animate-spin text-indigo-600" />
                      <span>Thinking through your request…</span>
                    </div>
                  </div>
                ) : null}
                <div ref={endOfMessagesRef} />
              </div>

              {error ? <p className="mx-4 mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 md:mx-7" role="alert">{error}</p> : null}

              <div className="border-t border-slate-200 bg-slate-50/70 p-4 md:px-7 md:py-5">
                <form className="flex items-end gap-3" onSubmit={onSubmit} ref={formRef}>
                  <label className="sr-only" htmlFor="copilot-question">Ask HR Copilot</label>
                  <textarea
                    className="max-h-36 min-h-[48px] flex-1 resize-y rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-100"
                    disabled={!authReady || sending}
                    id="copilot-question"
                    maxLength={2000}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={onInputKeyDown}
                    placeholder="Ask about a policy, HR data, or an action…"
                    rows={1}
                    value={draft}
                  />
                  <Button
                    className="h-12 shrink-0 gap-2 rounded-xl bg-indigo-600 px-4 text-white hover:bg-indigo-500"
                    disabled={!authReady || sending || !draft.trim()}
                    type="submit"
                  >
                    {sending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                    <span className="hidden sm:inline">Send</span>
                  </Button>
                </form>
                <div className="mt-2 flex justify-between text-[11px] text-slate-400">
                  <span>Enter to send · Shift+Enter for a new line</span>
                  <span>{draft.length}/2000</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>
    </main>
  );
}
