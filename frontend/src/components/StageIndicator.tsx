export interface StageLine {
  key: string;
  text: string;
  state: "running" | "done";
}

interface Props {
  lines: StageLine[];
  onCancel: () => void;
}

export function StageIndicator({ lines, onCancel }: Props) {
  return (
    <div className="stages">
      {lines.map((line) => (
        <div className={`stage-row ${line.state === "running" ? "active" : "done"}`} key={line.key}>
          {line.state === "running" ? <span className="spinner" /> : <span className="tick">✓</span>}
          {line.text}
        </div>
      ))}
      <div className="actions" style={{ marginTop: 14 }}>
        <button className="btn btn-small btn-danger" onClick={onCancel}>
          Abbrechen
        </button>
      </div>
    </div>
  );
}
