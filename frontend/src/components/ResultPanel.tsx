import { downloadText } from "../lib/api";
import type { PromptBundle, PromptCritique, Variant } from "../types/api";
import { FieldBlock } from "./FieldBlock";

const VARIANT_ORDER: Variant[] = ["precise", "cinematic", "experimental"];

const FIELD_TITLES: Record<string, string> = {
  main_prompt: "Hauptprompt",
  negative_prompt: "Negativprompt",
  motion_prompt: "Bewegung",
  audio_prompt: "Audio",
  dialogue: "Dialog",
  camera_notes: "Kamera / Framing",
};

const FIELD_ORDER = [
  "main_prompt",
  "negative_prompt",
  "motion_prompt",
  "audio_prompt",
  "dialogue",
  "camera_notes",
] as const;

interface Props {
  critique: PromptCritique | null;
  bundles: PromptBundle[];
  active: Variant;
  labels: Record<Variant, string>;
  onSelect: (variant: Variant) => void;
  onReuse: (text: string) => void;
  requestedVariants: Variant[];
}

export function ResultPanel({
  critique,
  bundles,
  active,
  labels,
  onSelect,
  onReuse,
  requestedVariants,
}: Props) {
  const bundle = bundles.find((entry) => entry.variant === active);
  const tabs = VARIANT_ORDER.filter((variant) => requestedVariants.includes(variant));

  function fullText(entry: PromptBundle): string {
    return FIELD_ORDER.filter((field) => entry[field])
      .map((field) => `## ${FIELD_TITLES[field]}\n${entry[field]}`)
      .join("\n\n");
  }

  return (
    <>
      {critique && <CritiquePanel critique={critique} />}

      <div className="tabs">
        {tabs.map((variant) => {
          const ready = bundles.find((entry) => entry.variant === variant);
          return (
            <button
              key={variant}
              role="tab"
              aria-selected={variant === active}
              disabled={!ready}
              onClick={() => onSelect(variant)}
            >
              {ready?.variant_label ?? labels[variant]}
              {!ready && " …"}
            </button>
          );
        })}
      </div>

      {!bundle && <p className="empty">Diese Variante wird noch komponiert.</p>}

      {bundle && (
        <>
          {FIELD_ORDER.filter((field) => bundle[field]).map((field) => (
            <FieldBlock
              key={field}
              title={FIELD_TITLES[field]}
              text={bundle[field] as string}
              meta={
                field === "main_prompt"
                  ? `${bundle.char_count} Zeichen${
                      bundle.duration_ms ? ` · ${(bundle.duration_ms / 1000).toFixed(1)} s` : ""
                    }`
                  : undefined
              }
            />
          ))}

          {bundle.warnings.length > 0 && (
            <div className="panel">
              <span className="block-title">Warnungen</span>
              <ul className="list warn">
                {bundle.warnings.map((warning, index) => (
                  <li key={index}>{warning}</li>
                ))}
              </ul>
            </div>
          )}

          {bundle.rationale.length > 0 && (
            <details className="panel">
              <summary>Was geändert wurde</summary>
              <ul className="list">
                {bundle.rationale.map((line, index) => (
                  <li key={index}>{line}</li>
                ))}
              </ul>
            </details>
          )}

          <div className="actions" style={{ marginTop: 14 }}>
            <button className="btn btn-small" onClick={() => onReuse(bundle.main_prompt)}>
              Als Ausgangsprompt übernehmen
            </button>
            <button
              className="btn btn-small"
              onClick={() =>
                downloadText(`prompt_${bundle.profile_id}_${bundle.variant}.txt`, fullText(bundle))
              }
            >
              Als .txt speichern
            </button>
          </div>
        </>
      )}
    </>
  );
}

function CritiquePanel({ critique }: { critique: PromptCritique }) {
  const groups: [string, string[]][] = [
    ["Das trägt schon", critique.strengths],
    ["Das hält nicht", critique.weaknesses],
    ["Das fehlt", critique.missing],
  ];

  return (
    <details className="panel" open>
      <summary>Analyse des Ausgangsprompts</summary>
      {critique.summary && <p className="summary-line" style={{ marginTop: 12 }}>{critique.summary}</p>}
      {groups
        .filter(([, items]) => items.length > 0)
        .map(([title, items]) => (
          <div key={title}>
            <p className="group-title">{title}</p>
            <ul className="list">
              {items.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </div>
        ))}
    </details>
  );
}
