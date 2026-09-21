import type { ProviderCheck } from "../types/api";

function toneOf(status: ProviderCheck["status"]): string {
  if (status === "ok") return "ok";
  return status === "fail" ? "fail" : "warn";
}

interface Props {
  checks: ProviderCheck[];
}

/** Einzelpruefungen aus `POST /api/provider/test` - gleiche Darstellung ueberall. */
export function CheckList({ checks }: Props) {
  if (checks.length === 0) return null;
  return (
    <div className="status-checks">
      {checks.map((check) => (
        <div className="status-check" key={check.id}>
          <span className={`dot ${toneOf(check.status)}`} />
          <span>
            <strong style={{ fontWeight: 600 }}>{check.label}:</strong> {check.message}
          </span>
        </div>
      ))}
    </div>
  );
}
