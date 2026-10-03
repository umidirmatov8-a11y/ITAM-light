import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { ConfigProvider, theme as antdTheme, App as AntApp } from 'antd';
import ruRU from 'antd/locale/ru_RU';
import enUS from 'antd/locale/en_US';
import uzUZ from 'antd/locale/uz_UZ';
import { useTranslation } from 'react-i18next';

type Mode = 'light' | 'dark';
const ThemeContext = createContext<{ mode: Mode; toggle: () => void }>({ mode: 'light', toggle: () => undefined });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<Mode>(() => {
    try {
      const saved = localStorage.getItem('itam.theme');
      if (saved === 'dark' || saved === 'light') return saved;
    } catch {
      /* ignore */
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  const { i18n } = useTranslation();
  useEffect(() => {
    document.documentElement.dataset.theme = mode;
    try {
      localStorage.setItem('itam.theme', mode);
    } catch {
      /* ignore */
    }
  }, [mode]);
  const locale = i18n.language === 'en' ? enUS : i18n.language === 'uz' ? uzUZ : ruRU;
  return (
    <ThemeContext.Provider value={{ mode, toggle: () => setMode((m) => (m === 'light' ? 'dark' : 'light')) }}>
      <ConfigProvider
        locale={locale}
        theme={{
          algorithm: mode === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
          token: { colorPrimary: '#1d4ed8', borderRadius: 8, fontFamily: "'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif" },
          components: { Layout: { headerHeight: 56, siderBg: mode === 'dark' ? '#0f172a' : '#0b1f4d', triggerBg: '#0a1838' }, Menu: { darkItemBg: 'transparent' } },
        }}
      >
        <AntApp>{children}</AntApp>
      </ConfigProvider>
    </ThemeContext.Provider>
  );
}

export const useThemeMode = () => useContext(ThemeContext);
