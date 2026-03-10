import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import he from "./locales/he.json";

const savedLanguage = localStorage.getItem("language") || "en";

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    he: { translation: he },
  },
  lng: savedLanguage,
  fallbackLng: "en",
  interpolation: {
    escapeValue: false,
  },
});

// Apply direction and lang on init and language change
function applyDirection(lng: string) {
  const dir = lng === "he" ? "rtl" : "ltr";
  document.documentElement.dir = dir;
  document.documentElement.lang = lng;
}

applyDirection(savedLanguage);

i18n.on("languageChanged", (lng: string) => {
  localStorage.setItem("language", lng);
  applyDirection(lng);
});

export default i18n;
