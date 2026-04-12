import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Search } from "lucide-react";
import { Modal } from "../common/Modal";
import { EMOJI_DATA } from "./emojiData";

interface IconPickerModalProps {
  isOpen: boolean;
  onClose: () => void;
  category: string;
  currentIcon: string;
  onSave: (icon: string) => void;
}

export function IconPickerModal({ isOpen, onClose, category, currentIcon, onSave }: IconPickerModalProps) {
  const { t } = useTranslation();
  const [tempIcon, setTempIcon] = useState(currentIcon);
  const [emojiSearch, setEmojiSearch] = useState("");

  const query = emojiSearch.toLowerCase().trim();
  const filtered = query
    ? EMOJI_DATA.filter(([, kw]) => kw.includes(query))
    : EMOJI_DATA;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`${t("categories.changeIconFor")} ${category}`}
      maxWidth="md"
    >
      <div className="p-4 md:p-6 space-y-4 md:space-y-6 overflow-y-auto">
        <div className="relative">
          <Search size={16} className="absolute inset-inline-start-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="text"
            placeholder={t("categories.searchEmojis")}
            value={emojiSearch}
            onChange={(e) => setEmojiSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
            className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl ps-9 pe-4 py-2 text-sm outline-none focus:border-[var(--primary)] transition-all"
          />
        </div>

        <div>
          {filtered.length > 0 ? (
            <div className="grid grid-cols-6 md:grid-cols-8 gap-1.5 md:gap-2 max-h-[220px] md:max-h-[280px] overflow-y-auto p-1">
              {filtered.map(([emoji]) => (
                <button
                  key={emoji}
                  onClick={() => setTempIcon(emoji)}
                  className={`w-10 h-10 flex items-center justify-center rounded-lg bg-[var(--surface-base)] border transition-all text-xl ${
                    tempIcon === emoji
                      ? "border-[var(--primary)] bg-[var(--primary)]/20"
                      : "border-[var(--surface-light)] hover:border-[var(--primary)] hover:bg-[var(--primary)]/10"
                  }`}
                >
                  {emoji}
                </button>
              ))}
            </div>
          ) : (
            <p className="text-sm text-[var(--text-muted)] text-center py-6">
              {t("categories.noEmojisMatch")}
            </p>
          )}
        </div>

        <div>
          <p className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider mb-3">
            {t("categories.customEmojiOrText")}
          </p>
          <input
            type="text"
            maxLength={4}
            value={tempIcon}
            onChange={(e) => setTempIcon(e.target.value)}
            className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 text-2xl text-center outline-none focus:border-[var(--primary)] transition-all"
            onKeyDown={(e) => {
              if (e.key === "Enter" && tempIcon) onSave(tempIcon);
              if (e.key === "Escape") onClose();
            }}
          />
        </div>
      </div>

      <div className="px-4 md:px-6 py-4 border-t border-[var(--surface-light)] flex gap-3 shrink-0">
        <button
          onClick={onClose}
          className="flex-1 py-2 text-sm font-bold hover:text-white transition-colors"
        >
          {t("common.cancel")}
        </button>
        <button
          onClick={() => { if (tempIcon) onSave(tempIcon); }}
          className="flex-1 py-2 bg-[var(--primary)] rounded-xl text-white font-bold hover:bg-[var(--primary-dark)] transition-all"
        >
          {t("common.save")}
        </button>
      </div>
    </Modal>
  );
}
