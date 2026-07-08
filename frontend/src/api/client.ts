const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api";

export interface DocumentStatusResponse {
  id: string;
  filename: string;
  status: string;
}

export interface Escort {
  escort_type: string;
  mandatory: boolean;
}

export interface Segment {
  route_order: number;
  from_location: string | null;
  to_location: string | null;
  road_type: string | null;
  bundesland: string | null;
  escorts: Escort[];
}

export interface Condition {
  category: string;
  raw_text: string;
  structured_value: unknown;
  confidence: number;
  needs_review: boolean;
}

export interface Permit {
  id: string;
  permit_number: string | null;
  authority: string | null;
  legal_basis: string[] | null;
  issue_date: string | null;
  valid_until: string | null;
  status: string;
  confidence: number;
  segments: Segment[];
  conditions: Condition[];
}

export async function uploadDocument(file: File): Promise<DocumentStatusResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/documents`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Upload failed" }));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

export async function fetchPermits(): Promise<Permit[]> {
  const res = await fetch(`${API_BASE}/permits`);
  if (!res.ok) throw new Error("Failed to load permits");
  return res.json();
}

export async function fetchPermit(id: string): Promise<Permit> {
  const res = await fetch(`${API_BASE}/permits/${id}`);
  if (!res.ok) throw new Error("Failed to load permit");
  return res.json();
}

export async function sendChatMessage(
  permitId: string,
  message: string
): Promise<{ answer: string; citations: string[] }> {
  const res = await fetch(`${API_BASE}/permits/${permitId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) throw new Error("Chat request failed");
  return res.json();
}
