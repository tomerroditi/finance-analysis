import { CreditCard, Landmark, Shield, type LucideProps } from "lucide-react";
import { useState, type ComponentType } from "react";

/**
 * Eagerly import every file under `assets/provider-logos/` and expose them as
 * a basename → URL lookup. Keys are normalised to lowercase, hyphens preserved,
 * so the provider key `"visa cal"` (spaces) maps to file `visa-cal.svg` once
 * we replace whitespace at lookup time.
 */
const LOGO_MODULES = import.meta.glob<string>(
  "../../assets/provider-logos/*.{svg,png}",
  { eager: true, query: "?url", import: "default" },
);

const LOGO_BY_KEY: Record<string, string> = Object.fromEntries(
  Object.entries(LOGO_MODULES).map(([path, url]) => {
    const basename = path
      .split("/")
      .pop()!
      .replace(/\.(svg|png)$/i, "")
      .toLowerCase();
    return [basename, url];
  }),
);

const SERVICE_FALLBACK_ICONS: Record<string, ComponentType<LucideProps>> = {
  banks: Landmark,
  credit_cards: CreditCard,
  insurances: Shield,
};

interface ProviderLogoProps {
  /** Provider key from the backend, e.g. "hapoalim", "visa cal". */
  provider: string;
  /** Service key (banks / credit_cards / insurances) used for the fallback icon. */
  service: string;
  /** Pixel size of the rendered logo or fallback icon. Default 32. */
  size?: number;
  /** Extra classes on the rendered element. */
  className?: string;
  /**
   * Alt text for the image. Default is an empty string (decorative — the
   * provider name is typically rendered next to the logo).
   */
  alt?: string;
}

/**
 * Renders a financial-provider logo for a known provider (Hapoalim, Leumi,
 * Max, …). Falls back to a generic service icon (Landmark for banks,
 * CreditCard for credit cards, Shield for insurance) when the logo file is
 * missing or fails to load.
 *
 * Provider keys with spaces (e.g. ``"visa cal"``) map to hyphenated
 * filenames (``visa-cal.svg``). Logo files live in
 * ``src/assets/provider-logos/`` and are statically imported by Vite, so
 * adding a new logo is just dropping a file into that folder.
 */
export function ProviderLogo({
  provider,
  service,
  size = 32,
  className = "",
  alt = "",
}: ProviderLogoProps) {
  const [imageFailed, setImageFailed] = useState(false);

  const key = provider.toLowerCase().replace(/\s+/g, "-");
  const url = LOGO_BY_KEY[key];

  if (!url || imageFailed) {
    const Icon = SERVICE_FALLBACK_ICONS[service] ?? CreditCard;
    return <Icon size={size} className={className} aria-hidden="true" />;
  }

  return (
    <img
      src={url}
      alt={alt}
      width={size}
      height={size}
      style={{ width: size, height: size, objectFit: "contain" }}
      className={className}
      onError={() => setImageFailed(true)}
    />
  );
}
