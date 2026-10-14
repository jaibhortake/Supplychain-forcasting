import { useMutation, useQuery } from "@tanstack/react-query";
import { Bot, ChevronDown, Loader2, Send, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { ChatMessage } from "../api/types";
import { Callout, PageHeader } from "../components/ui";

interface Turn extends ChatMessage {
  facts?: string;
  grounded?: string[];
  error?: boolean;
}

const SUGGESTIONS = [
  "Why is TV demand in the North going up over the next few weeks?",
  "How much AC-X1 stock should I keep in the South?",
  "Which products and regions had unusual sales recently?",
  "How accurate are our refrigerator forecasts in the East?",
];

function Facts({ facts, grounded }: { facts: string; grounded?: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300" onClick={() => setOpen(!open)}>
        <ChevronDown className={`size-3.5 transition ${open ? "rotate-180" : ""}`} />
        Based on: {grounded?.join(", ")}
      </button>
      {open && (
        <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-50 p-3 text-xs whitespace-pre-wrap text-slate-600 dark:bg-slate-950 dark:text-slate-400">
          {facts}
        </pre>
      )}
    </div>
  );
}

export default function Assistant() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const health = useQuery({ queryKey: ["health"], queryFn: api.health });

  const ask = useMutation({
    mutationFn: (message: string) =>
      api.chat(
        message,
        turns.filter((t) => t.error!).map(({ role, content }) => ({ role, content })),
      ),
    onSuccess: (r) => setTurns((t) => [...t, { role: "assistant", content: r.answer, facts: r.facts, grounded: r.grounded_on }]),
    onError: (e) => setTurns((t) => [...t, { role: "assistant", content: e instanceof Error ? e.message : String(e), error: true }]),
  });

  useEffect(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), [turns, ask.isPending]);

  const send = (text: string) => {
    const msg = text.trim();
    if (!msg || ask.isPending) return;
    setTurns((t) => [...t, { role: "user", content: msg }]);
    setInput("");
    ask.mutate(msg);
  };

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col lg:h-[calc(100vh-4rem)]">
      <PageHeader
        title="Ask the forecast"
        subtitle="Plain-English questions, answered from the system's own numbers by a local AI model (Ollama). Your data never leaves your machine."
      />
      {health.data && !health.data.llm.available && (
        <div className="mb-4">
          <Callout>
            The AI model isn't running. Start it with <code>ollama serve</code> and download the model once with{" "}
            <code>ollama pull {health.data.llm.model}</code>. Every other page works without it.
          </Callout>
        </div>
      )}

      <div className="card flex min-h-0 flex-1 flex-col">
        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {turns.length === 0 && (
            <div className="mx-auto max-w-xl py-8 text-center">
              <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300">
                <Bot className="size-6" />
              </div>
              <p className="mt-3 font-medium">What would you like to know?</p>
              <div className="mt-5 grid gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    className="rounded-xl border border-slate-200 p-3 text-left text-sm text-slate-600 transition hover:border-indigo-300 hover:bg-indigo-50/50 dark:border-slate-700 dark:text-slate-300 dark:hover:border-indigo-700 dark:hover:bg-indigo-950/40"
                    onClick={() => send(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}
          {turns.map((t, i) => (
            <div key={i} className={`flex gap-3 ${t.role === "user" ? "justify-end" : ""}`}>
              {t.role === "assistant" && (
                <div className="grid size-8 shrink-0 place-items-center rounded-full bg-indigo-600 text-white">
                  <Bot className="size-4" />
                </div>
              )}
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                  t.role === "user"
                    ? "bg-indigo-600 text-white"
                    : t.error
                      ? "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200"
                      : "bg-slate-100 dark:bg-slate-800"
                }`}
              >
                <div className="whitespace-pre-wrap leading-relaxed">{t.content}</div>
                {t.facts && <Facts facts={t.facts} grounded={t.grounded} />}
              </div>
              {t.role === "user" && (
                <div className="grid size-8 shrink-0 place-items-center rounded-full bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-200">
                  <User className="size-4" />
                </div>
              )}
            </div>
          ))}
          {ask.isPending && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="size-4 animate-spin" /> Thinking… (the first answer can take a minute while the model loads)
            </div>
          )}
          <div ref={endRef} />
        </div>
        <form
          className="flex gap-2 border-t border-slate-100 p-3 dark:border-slate-800"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            className="input"
            placeholder="Ask about a product, region, event or stock level…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            maxLength={2000}
          />
          <button className="btn-primary" type="submit" disabled={!input.trim() || ask.isPending} aria-label="Send">
            <Send className="size-4" />
          </button>
        </form>
      </div>
    </div>
  );
}
