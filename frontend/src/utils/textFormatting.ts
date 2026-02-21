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
