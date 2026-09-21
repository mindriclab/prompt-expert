import { useRef, useState } from "react";
import { deleteImage, uploadImage } from "../lib/api";
import type { ReferenceItem, Role } from "../types/api";

const ROLE_LABELS: Record<Role, string> = {
  subject: "Subjekt",
  style: "Stil",
  composition: "Komposition",
  wardrobe: "Kleidung / Detail",
  environment: "Umgebung",
};

const ROLE_HINTS: Record<Role, string> = {
  subject: "Person oder Hauptobjekt: Aussehen, Körper, Kleidung, Pose",
  style: "nur der Look: Rendering, Grade, Korn — nicht der Inhalt",
  composition: "Bildaufbau, Kamerawinkel, Anordnung im Bild",
  wardrobe: "Kleidung, Materialien und Accessoires im Detail",
  environment: "Ort, Hintergrund, Requisiten, Tageszeit, Wetter",
};

interface Props {
  max: number;
  items: ReferenceItem[];
  onChange: (items: ReferenceItem[]) => void;
  onError: (message: string) => void;
  disabled: boolean;
}

export function ReferenceStrip({ max, items, onChange, onError, disabled }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const free = max - items.length;

  async function addFiles(files: FileList | File[]) {
    const list = Array.from(files).slice(0, free);
    if (list.length === 0) {
      onError(
        max === 1
          ? "Ein Startframe ist genau ein Bild. Erst das vorhandene entfernen."
          : `Mehr als ${max} Referenzbilder gehen nicht.`,
      );
      return;
    }
    setBusy(true);
    const added: ReferenceItem[] = [];
    for (const file of list) {
      try {
        const stored = await uploadImage(file);
        added.push({ ...stored, role: items.length + added.length === 0 ? "subject" : "style" });
      } catch (error) {
        onError(`${file.name}: ${(error as Error).message}`);
      }
    }
    setBusy(false);
    if (added.length > 0) onChange([...items, ...added]);
  }

  function setRole(id: string, role: Role) {
    onChange(items.map((item) => (item.id === id ? { ...item, role } : item)));
  }

  async function remove(id: string) {
    onChange(items.filter((item) => item.id !== id));
    await deleteImage(id);
  }

  function moveTo(target: number) {
    if (dragIndex === null || dragIndex === target) return;
    const next = [...items];
    const [moved] = next.splice(dragIndex, 1);
    next.splice(target, 0, moved);
    setDragIndex(null);
    onChange(next);
  }

  return (
    <>
      <div
        className={`dropzone ${dragOver ? "over" : ""} ${disabled ? "disabled" : ""}`}
        onDragOver={(event) => {
          event.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragOver(false);
          if (!disabled && event.dataTransfer.files.length > 0) void addFiles(event.dataTransfer.files);
        }}
        onClick={() => !disabled && fileInput.current?.click()}
      >
        <input
          ref={fileInput}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          hidden
          onChange={(event) => {
            if (event.target.files) void addFiles(event.target.files);
            event.target.value = "";
          }}
        />
        {busy ? (
          <span className="stage-row active">
            <span className="spinner" /> Bilder werden vorbereitet
          </span>
        ) : (
          <>
            <strong>{max === 1 ? "Startframe hierher ziehen" : "Referenzbilder hierher ziehen"}</strong>
            <span className="hint">
              JPEG, PNG oder WebP ·{" "}
              {max === 1 ? "ein Bild" : `noch ${free} von ${max} frei`} · bleiben lokal
            </span>
          </>
        )}
      </div>

      {items.length > 0 && (
        <div className="refs">
          {items.map((item, index) => (
            <div
              className={`ref ${dragIndex === index ? "dragging" : ""}`}
              key={item.id}
              draggable={!disabled}
              onDragStart={() => setDragIndex(index)}
              onDragOver={(event) => event.preventDefault()}
              onDrop={() => moveTo(index)}
              onDragEnd={() => setDragIndex(null)}
            >
              <img src={item.thumb_url} alt={item.original_name} />
              <div className="ref-body">
                <div className="ref-name" title={item.original_name}>
                  {index + 1}. {item.original_name}
                </div>
                <select
                  value={item.role}
                  disabled={disabled}
                  onChange={(event) => setRole(item.id, event.target.value as Role)}
                >
                  {(Object.keys(ROLE_LABELS) as Role[]).map((role) => (
                    <option key={role} value={role}>
                      {ROLE_LABELS[role]}
                    </option>
                  ))}
                </select>
                <div className="ref-meta">
                  {ROLE_HINTS[item.role]}
                  <br />
                  {item.width}×{item.height} · {Math.round(item.bytes / 1024)} kB
                </div>
              </div>
              <button
                className="btn btn-small btn-danger"
                disabled={disabled}
                onClick={() => void remove(item.id)}
                title="Entfernen"
              >
                ✕
              </button>
            </div>
          ))}
          {max > 1 && (
            <p className="hint">
              Ziehen ändert die Reihenfolge. Die erste Referenz wiegt am schwersten.
            </p>
          )}
        </div>
      )}
    </>
  );
}
