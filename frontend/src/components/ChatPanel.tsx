import { useState } from "react";
import { sendChatMessage } from "../api/client";

interface Props {
  permitId: string | null;
}

interface Message {
  role: "user" | "assistant";
  content: string;
}

export default function ChatPanel({ permitId }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const handleSend = async () => {
    if (!input.trim() || !permitId) return;
    const userMessage: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setSending(true);

    try {
      const res = await sendChatMessage(permitId, userMessage.content);
      setMessages((prev) => [...prev, { role: "assistant", content: res.answer }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Something went wrong answering that — try again." },
      ]);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="card chat-panel">
      <h2>Ask the permit copilot</h2>

      {!permitId && (
        <p className="empty-state">Upload and process a permit to start chatting.</p>
      )}

      {permitId && (
        <>
          <div className="chat-messages">
            {messages.length === 0 && (
              <p className="empty-state">
                Try: "Is night transport allowed?" or "What escort is required?"
              </p>
            )}
            {messages.map((m, idx) => (
              <div className={`chat-bubble ${m.role}`} key={idx}>
                {m.content}
              </div>
            ))}
            {sending && <div className="chat-bubble assistant">Thinking (Llama 3.1)…</div>}
          </div>
          <div className="chat-input-row">
            <input
              type="text"
              placeholder="Ask a question about this permit..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              aria-label="Chat message"
            />
            <button className="btn-primary" onClick={handleSend} disabled={sending}>
              Send
            </button>
          </div>
        </>
      )}
    </div>
  );
}
