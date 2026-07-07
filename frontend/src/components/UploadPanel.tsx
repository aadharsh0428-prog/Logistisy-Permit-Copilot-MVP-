import { useCallback, useState } from "react";
import { uploadDocument } from "../api/client";

interface Props {
  onProcessed: (documentId: string) => void;
}

export default function UploadPanel({ onProcessed }: Props) {
  const [dragging, setDragging] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setStatus(null);

      const validExtensions = [".pdf", ".png", ".jpg", ".jpeg"];
      const isValid = validExtensions.some((ext) =>
        file.name.toLowerCase().endsWith(ext)
      );
      if (!isValid) {
        setError("Unsupported file type. Please upload a PDF or image.");
        return;
      }

      try {
        setStatus("processing");
        const doc = await uploadDocument(file);
        setStatus(doc.status);
        onProcessed(doc.id);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Something went wrong.");
        setStatus(null);
      }
    },
    [onProcessed]
  );

  return (
    <div className="card">
      <h2>Upload permit document</h2>
      <div
        className={`upload-dropzone ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
        }}
      >
        <p style={{ color: "var(--color-text-muted)", fontSize: "0.9rem" }}>
          Drag &amp; drop a Schwertransport permit PDF or image here
        </p>
        <label className="file-label" htmlFor="file-input">
          Choose file
        </label>
        <input
          id="file-input"
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        />
      </div>

      {status && (
        <p style={{ marginTop: 14 }}>
          Status:{" "}
          <span className={`status-badge status-${status}`}>{status}</span>
        </p>
      )}
      {error && (
        <p style={{ marginTop: 10, color: "var(--color-error)", fontSize: "0.85rem" }}>
          {error}
        </p>
      )}
    </div>
  );
}
