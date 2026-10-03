import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import dayjs from 'dayjs';
import 'dayjs/locale/ru';
import 'dayjs/locale/en';
import 'dayjs/locale/uz-latn';
import ru from './ru';
import en from './en';
import uz from './uz';

export const LANGUAGES = [
  { code: 'ru', label: 'Русский' },
  { code: 'en', label: 'English' },
  { code: 'uz', label: "O'zbekcha" },
] as const;

const stored = (() => {
  try {
    return localStorage.getItem('itam.lang');
  } catch {
    return null;
  }
})();

i18n.use(initReactI18next).init({
  resources: { ru: { translation: ru }, en: { translation: en }, uz: { translation: uz } },
  lng: stored ?? 'ru',
  fallbackLng: 'ru',
  interpolation: { escapeValue: false },
  returnNull: false,
});

export const setLanguage = (lng: string) => {
  i18n.changeLanguage(lng);
  dayjs.locale(lng === 'uz' ? 'uz-latn' : lng);
  try {
    localStorage.setItem('itam.lang', lng);
  } catch {
    /* ignore */
  }
};

dayjs.locale((stored ?? 'ru') === 'uz' ? 'uz-latn' : stored ?? 'ru');

export default i18n;
