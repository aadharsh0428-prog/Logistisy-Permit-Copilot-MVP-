import { Permit } from "../api/client";
import ConditionsList from "./ConditionsList";

interface Props {
  permit: Permit | null;
  loading: boolean;
}

export default function PermitDashboard({ permit, loading }: Props) {
  if (loading) {
    return (
      <div className="card">
        <h2>Permit overview</h2>
        <p className="empty-state">Processing document with Llama 3.2 Vision…</p>
      </div>
    );
  }

  if (!permit) {
    return (
      <div className="card">
        <h2>Permit overview</h2>
        <p className="empty-state">
          Upload a permit to see structured route, conditions, and escort data here.
        </p>
      </div>
    );
  }

  const isExpired = permit.valid_until
    ? new Date(permit.valid_until) < new Date()
    : false;

  return (
    <div className="card">
      <h2>Permit overview</h2>

      <div className="permit-meta">
        <div className="meta-item">
          <div className="label">Permit number</div>
          <div className="value">{permit.permit_number || "—"}</div>
        </div>
        <div className="meta-item">
          <div className="label">Authority</div>
          <div className="value">{permit.authority || "—"}</div>
        </div>
        <div className="meta-item">
          <div className="label">Valid until</div>
          <div
            className="value"
            style={{ color: isExpired ? "var(--color-error)" : undefined }}
          >
            {permit.valid_until || "—"} {isExpired && "(EXPIRED)"}
          </div>
        </div>
        <div className="meta-item">
          <div className="label">Legal basis</div>
          <div className="value">
            {(permit.legal_basis || []).map((lb) => (
              <span className="legal-basis-chip" key={lb}>
                {lb}
              </span>
            ))}
          </div>
        </div>
      </div>

      <h2>Route segments</h2>
      {permit.segments.length === 0 && (
        <p className="empty-state">No route segments extracted.</p>
      )}
      {permit.segments.map((seg, idx) => (
        <div className="segment-row" key={idx}>
          <strong>{seg.route_order}.</strong>
          <span>
            {seg.from_location} → {seg.to_location} ({seg.road_type}, {seg.bundesland})
          </span>
          {seg.escorts.map((e, i) => (
            <span className="escort-tag" key={i}>
              {e.escort_type}
            </span>
          ))}
        </div>
      ))}

      <h2 style={{ marginTop: 20 }}>Conditions</h2>
      <ConditionsList conditions={permit.conditions} />
    </div>
  );
}
