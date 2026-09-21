import { useState } from "react";
import { copyText } from "../lib/api";

interface Props {
  title: string;
  text: string;
  meta?: string;
}

export function FieldBlock({ title, text, meta }: Props) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    const ok = await copyText(text);
    if (!ok) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  }

  return (
    <div className="block">
      <div className="block-head">
        <span className="block-title">{title}</span>
        <span className="actions">
          {meta && <span className="block-meta">{meta}</span>}
          {copied ? (
            <span className="copied">kopiert</span>
          ) : (
            <button className="btn btn-small" onClick={handleCopy}>
              Kopieren
            </button>
          )}
        </span>
      </div>
      <div className="block-body">{text}</div>
    </div>
  );
}
