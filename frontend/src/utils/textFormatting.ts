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

const SERVICE_LABELS: Record<string, string> = {
  credit_cards: "Credit Card",
  credit_card_transactions: "Credit Card",
  banks: "Bank",
  bank_transactions: "Bank",
  cash: "Cash",
  cash_transactions: "Cash",
  manual_investments: "Investment",
  manual_investment_transactions: "Investment",
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
};

export function humanizeService(service: string): string {
  return SERVICE_LABELS[service] ?? toTitleCase(service.replace(/_/g, " "));
}

export function humanizeProvider(provider: string): string {
  return PROVIDER_LABELS[provider] ?? toTitleCase(provider);
}

export function humanizeAccountType(service: string): string {
  return `${humanizeService(service)} Account`;
}
