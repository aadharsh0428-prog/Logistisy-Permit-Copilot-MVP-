import { useState } from "react";
import Header from "./components/Header";
import UploadPanel from "./components/UploadPanel";
import PermitDashboard from "./components/PermitDashboard";
import ChatPanel from "./components/ChatPanel";
import { fetchPermits, Permit } from "./api/client";

export default function App() {
  const [permit, setPermit] = useState<Permit | null>(null);
  const [loading, setLoading] = useState(false);

  const handleProcessed = async () => {
    setLoading(true);
    try {
      // MVP simplification: extraction runs synchronously on upload,
      // so the most recent permit is the one we just processed.
      const permits = await fetchPermits();
      setPermit(permits[0] || null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-shell">
      <Header />

      <section className="hero">
        <h1>Heavy transport permits, made understandable</h1>
        <p>
          Upload a Schwertransport permit and get structured routes, conditions,
          escort requirements, and a grounded copilot to answer questions — powered
          entirely by local, open-source AI.
        </p>
      </section>

      <main className="main-content">
        <div className="grid-two">
          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            <UploadPanel onProcessed={handleProcessed} />
            <ChatPanel permitId={permit?.id ?? null} />
          </div>
          <PermitDashboard permit={permit} loading={loading} />
        </div>
      </main>
    </div>
  );
}
