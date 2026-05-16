import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { UploadCloud } from "lucide-react";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = ".csv,.xlsx";

interface Props {
  onFile: (file: File) => void;
}

/**
 * Drag-and-drop file zone with click-to-browse fallback. Enforces
 * 10 MB size cap and .csv/.xlsx extension whitelist.
 */
export function UploadFileDropzone({ onFile }: Props) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);

  function validateAndEmit(file: File) {
    if (file.size > MAX_BYTES) {
      setError(t("dataSources.import.uploadFileTooLarge"));
      return;
    }
    const name = file.name.toLowerCase();
    if (!name.endsWith(".csv") && !name.endsWith(".xlsx")) {
      setError(t("dataSources.import.uploadUnsupportedType"));
      return;
    }
    setError(null);
    onFile(file);
  }

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragOver(false);
          const file = e.dataTransfer.files?.[0];
          if (file) validateAndEmit(file);
        }}
        className={`w-full flex flex-col items-center justify-center gap-2 p-8 rounded-2xl border-2 border-dashed transition-colors ${
          isDragOver
            ? "border-[var(--primary)] bg-[var(--primary)]/5"
            : "border-[var(--surface-light)]"
        }`}
      >
        <UploadCloud size={32} className="text-[var(--text-muted)]" />
        <span className="text-sm text-[var(--text-muted)]">
          {t("dataSources.import.uploadDropzoneHint")}
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) validateAndEmit(file);
          e.target.value = "";
        }}
      />
      {error && <div className="text-xs text-red-400">{error}</div>}
    </div>
  );
}
