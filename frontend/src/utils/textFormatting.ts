const INITIALISMS = new Set([
  "ATM", "BTB", "DJ", "GPT", "USA", "P2P", "TV", "PC", "ID",
]);

function processWord(word: string): string {
  if (!word) return word;
  if (INITIALISMS.has(word.toUpperCase())) return word.toUpperCase();
  if (word.includes("-")) {
    return word
      .split("-")
      .map((p) => (INITIALISMS.has(p.toUpperCase()) ? p.toUpperCase() : p.charAt(0).toUpperCase() + p.slice(1).toLowerCase()))
      .join("-");
  }
  return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
}

export function toTitleCase(text: string): string {
  if (!text || !text.trim()) return text;
  return text
    .split(/(\s+)/)
    .map((part) => (/^\s+$/.test(part) ? part : processWord(part)))
    .join("");
}

import i18n from "../i18n";

const SERVICE_KEY_MAP: Record<string, string> = {
  credit_cards: "creditCard",
  credit_card_transactions: "creditCard",
  banks: "bank",
  bank_transactions: "bank",
  cash: "cash",
  cash_transactions: "cash",
  manual_investments: "investment",
  manual_investment_transactions: "investment",
  insurances: "insurance",
  insurance_transactions: "insurance",
};

const PROVIDER_LABELS: Record<string, string> = {
  hapoalim: "Hapoalim",
  leumi: "Leumi",
  discount: "Discount",
  mizrahi: "Mizrahi",
  onezero: "One Zero",
  isracard: "Isracard",
  max: "Max",
  cal: "Cal",
  amex: "Amex",
  beyahad: "Beyahad Bishvilha",
  behatsdaa: "Behatsdaa",
  beinleumi: "Beinleumi",
  massad: "Massad",
  yahav: "Yahav",
  fibi: "First International",
  hafenix: "HaPhoenix",
};

const PROVIDER_LABELS_HE: Record<string, string> = {
  hapoalim: "הפועלים",
  leumi: "לאומי",
  discount: "דיסקונט",
  mizrahi: "מזרחי טפחות",
  onezero: "One Zero",
  isracard: "ישראכרט",
  max: "מקס",
  cal: "כאל",
  amex: "אמריקן אקספרס",
  beyahad: "ביחד בשבילך",
  behatsdaa: "בהצדעה",
  beinleumi: "הבינלאומי",
  massad: "מסד",
  yahav: "יהב",
  fibi: "הבינלאומי הראשון",
  hafenix: "הפניקס",
};

export function humanizeService(service: string): string {
  const key = SERVICE_KEY_MAP[service];
  return key ? i18n.t(`services.${key}`) : toTitleCase(service.replace(/_/g, " "));
}

export function humanizeProvider(provider: string): string {
  const labels = i18n.language === "he" ? PROVIDER_LABELS_HE : PROVIDER_LABELS;
  return labels[provider] ?? toTitleCase(provider);
}

export function humanizeAccountType(service: string): string {
  return `${humanizeService(service)} ${i18n.t("common.account")}`;
}
