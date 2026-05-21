import type { HtmlPreview } from "../lib/types";

type HtmlPreviewPanelProps = {
  copiedItemId: string | null;
  preview: HtmlPreview;
  onClose: () => void;
  onCopySource: (content: string, itemId: string) => void;
};

export function HtmlPreviewPanel({
  copiedItemId,
  preview,
  onClose,
  onCopySource,
}: HtmlPreviewPanelProps) {
  return (
    <aside className="html-preview-panel" aria-label="HTML preview">
      <div className="html-preview-header">
        <div>
          <span>HTML preview</span>
          <small>Rendered output and source</small>
        </div>
        <button className="html-preview-close" type="button" onClick={onClose}>
          Close
        </button>
      </div>
      <div className="html-preview-body">
        <section className="html-preview-frame-section" aria-label="Rendered HTML">
          <iframe
            className="html-preview-frame"
            title="Rendered HTML preview"
            sandbox=""
            srcDoc={preview.html}
          />
        </section>
        <section className="html-preview-source-section" aria-label="HTML source">
          <div className="html-preview-section-title">
            <span>Source</span>
            <button
              className="copy-button compact"
              type="button"
              onClick={() => onCopySource(preview.html, "html-preview-source")}
            >
              <span className="copy-button-icon" aria-hidden="true" />
              {copiedItemId === "html-preview-source" ? "Copied" : "Copy source"}
            </button>
          </div>
          <pre>
            <code>{preview.html}</code>
          </pre>
        </section>
      </div>
    </aside>
  );
}
