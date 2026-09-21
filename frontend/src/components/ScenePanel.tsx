import type { SceneSpec } from "../types/api";

const ROLE_LABELS: Record<string, string> = {
  subject: "Subjekt",
  style: "Stil",
  composition: "Komposition",
  wardrobe: "Kleidung",
  environment: "Umgebung",
};

interface Row {
  label: string;
  value: string;
}

function rows(entries: [string, string | string[]][]): Row[] {
  return entries
    .map(([label, value]) => ({
      label,
      value: Array.isArray(value) ? value.join(", ") : value,
    }))
    .filter((row) => row.value.trim().length > 0);
}

export function ScenePanel({ scene }: { scene: SceneSpec }) {
  const groups: [string, Row[]][] = [
    [
      "Szene",
      rows([
        ["Ort", scene.scene.setting],
        ["Tageszeit", scene.scene.time_of_day],
        ["Atmosphäre", scene.scene.atmosphere],
        ["Requisiten", scene.scene.props],
      ]),
    ],
    [
      "Bild",
      rows([
        ["Stil", scene.visual.style],
        ["Komposition", scene.visual.composition],
        ["Licht", scene.visual.lighting],
        ["Farbwelt", scene.visual.palette],
        ["Material", scene.visual.materials],
      ]),
    ],
    [
      "Kamera",
      rows([
        ["Einstellung", scene.camera.shot],
        ["Objektiv", scene.camera.lens],
        ["Winkel", scene.camera.angle],
        ["Fokus", scene.camera.focus],
        ["Schärfentiefe", scene.camera.depth_of_field],
      ]),
    ],
  ];

  return (
    <details className="panel">
      <summary>Was im Bild erkannt wurde</summary>

      {scene.subjects.map((subject, index) => {
        const detail = rows([
          ["Aussehen", subject.appearance],
          ["Statur", subject.build],
          ["Haare", subject.hair],
          ["Gesicht", subject.face],
          ["Kleidung", subject.wardrobe],
          ["Pose", subject.pose],
          ["Ausdruck", subject.expression],
          ["Explizites Detail", subject.explicit_detail],
          ["Kontinuität", subject.continuity_features],
        ]);
        if (detail.length === 0) return null;
        return (
          <div key={index}>
            <p className="group-title">
              Subjekt {index + 1} · aus Referenz „{ROLE_LABELS[subject.role] ?? subject.role}"
            </p>
            <dl className="spec">
              {detail.map((row) => (
                <div key={row.label}>
                  <dt>{row.label}</dt>
                  <dd>{row.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        );
      })}

      {groups
        .filter(([, entries]) => entries.length > 0)
        .map(([title, entries]) => (
          <div key={title}>
            <p className="group-title">{title}</p>
            <dl className="spec">
              {entries.map((row) => (
                <div key={row.label}>
                  <dt>{row.label}</dt>
                  <dd>{row.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}

      {scene.uncertainties.length > 0 && (
        <>
          <p className="group-title">Unsicher — nicht als Tatsache übernommen</p>
          <ul className="list warn">
            {scene.uncertainties.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </>
      )}
    </details>
  );
}
