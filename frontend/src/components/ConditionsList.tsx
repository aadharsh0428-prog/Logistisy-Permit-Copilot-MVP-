import { Condition } from "../api/client";

interface Props {
  conditions: Condition[];
}

const categoryLabels: Record<string, string> = {
  time_window: "Time Window",
  escort: "Escort",
  load: "Load / Axle",
  weather: "Weather",
  other: "Other",
};

export default function ConditionsList({ conditions }: Props) {
  if (conditions.length === 0) {
    return <p className="empty-state">No conditions extracted yet.</p>;
  }

  return (
    <div>
      {conditions.map((c, idx) => (
        <div className="condition-item" key={idx}>
          <div className="condition-top">
            <span className="category-label">
              {categoryLabels[c.category] || c.category}
            </span>
            <div
              className="confidence-bar"
              aria-label={`Confidence ${Math.round(c.confidence * 100)}%`}
            >
              <div
                className={`confidence-fill ${c.confidence < 0.7 ? "low" : ""}`}
                style={{ width: `${Math.round(c.confidence * 100)}%` }}
              />
            </div>
          </div>
          <p style={{ fontSize: "0.9rem" }}>{c.raw_text}</p>
          {c.needs_review && (
            <p className="review-flag">⚠ Needs human review (low confidence)</p>
          )}
        </div>
      ))}
    </div>
  );
}
