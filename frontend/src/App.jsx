import React, { useState, useEffect, useCallback } from 'react';
import Navbar from './components/Navbar';
import MockExportBanner from './components/MockExportBanner';
import ErrorBoundary from './components/ErrorBoundary';
import { ToastProvider } from './components/Toast';
import { ConfirmProvider } from './components/ConfirmDialog';
import Settings from './pages/Settings';
import RFPTracker from './pages/RFPTracker';
import NewRFP from './pages/NewRFP';
import RFPDetail from './pages/RFPDetail';
import KnowledgeBase from './pages/KnowledgeBase';
import { api } from './services/api';

const THEME_KEY = 'rfp_theme';

function parseHash(hash) {
  const clean = hash.replace(/^#\/?/, '').trim();
  if (!clean || clean === 'tracker') {
    return { route: 'tracker', params: {} };
  }
  if (clean === 'new-rfp') {
    return { route: 'new-rfp', params: {} };
  }
  const rfpMatch = clean.match(/^rfp\/([^/?#]+)/);
  if (rfpMatch) {
    return { route: 'rfp-detail', params: { id: rfpMatch[1] } };
  }
  if (['kb', 'pricing', 'services', 'settings'].includes(clean)) {
    return { route: clean, params: {} };
  }
  return { route: 'tracker', params: {} };
}

/** The only place the theme is written: a single class on <html>. */
function applyTheme(isDark) {
  document.documentElement.classList.toggle('dark', isDark);
  localStorage.setItem(THEME_KEY, isDark ? 'dark' : 'light');
}

export default function App() {
  const [currentView, setCurrentView] = useState(() => parseHash(window.location.hash));
  const [apiConnected, setApiConnected] = useState(false);
  const [mockExportActive, setMockExportActive] = useState(true);
  const [isDark, setIsDark] = useState(() => {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) return saved === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  useEffect(() => {
    applyTheme(isDark);
  }, [isDark]);

  // Follow OS preference changes until the user has made an explicit choice
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    function onChange(e) {
      if (!localStorage.getItem(THEME_KEY)) setIsDark(e.matches);
    }
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);

  useEffect(() => {
    function handleHashChange() {
      setCurrentView(parseHash(window.location.hash));
    }
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      const res = await api.getHealth();
      setApiConnected(Boolean(res && res.status === 'ok'));
    } catch {
      setApiConnected(false);
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, [checkHealth]);

  useEffect(() => {
    api
      .getSettings()
      .then((s) => {
        if (s && s.mock_google_export !== undefined) setMockExportActive(Boolean(s.mock_google_export));
      })
      .catch(() => {});
  }, []);

  function navigate(route, params = {}) {
    if (route === 'rfp-detail' || route === 'rfp') {
      window.location.hash = `#/rfp/${params.id}`;
      setCurrentView({ route: 'rfp-detail', params: { id: String(params.id) } });
      return;
    }
    window.location.hash = route === 'tracker' ? '#/' : `#/${route}`;
    setCurrentView({ route, params: {} });
    window.scrollTo({ top: 0 });
  }

  function handleSettingsUpdated(newSettings) {
    if (newSettings && newSettings.mock_google_export !== undefined) {
      setMockExportActive(Boolean(newSettings.mock_google_export));
    }
  }

  const activeNavTab =
    currentView.route === 'rfp-detail' ? 'tracker' : ['services', 'pricing'].includes(currentView.route) ? 'settings' : currentView.route;

  return (
    <ToastProvider>
      <ConfirmProvider>
        <div className="min-h-screen bg-canvas text-ink flex flex-col font-sans transition-colors">
          <a href="#main-content" className="sr-only-focusable fixed top-2 left-2 z-[70] btn-primary">
            Skip to main content
          </a>

          {mockExportActive && <MockExportBanner onGoToSettings={() => navigate('settings')} />}

          <Navbar
            activeTab={activeNavTab}
            onSelectTab={(tab) => navigate(tab)}
            apiConnected={apiConnected}
            mockExportActive={mockExportActive}
            isDark={isDark}
            onToggleDark={() => setIsDark((d) => !d)}
          />

          <main id="main-content" tabIndex={-1} className="flex-1 pb-16 outline-none">
            <ErrorBoundary onReset={() => navigate('tracker')}>
              {currentView.route === 'tracker' && (
                <RFPTracker onSelectRFP={(id) => navigate('rfp-detail', { id })} onNewRFP={() => navigate('new-rfp')} />
              )}
              {currentView.route === 'new-rfp' && (
                <NewRFP onSuccess={(id) => navigate('rfp-detail', { id })} onCancel={() => navigate('tracker')} />
              )}
              {currentView.route === 'rfp-detail' && <RFPDetail rfpId={currentView.params.id} onBack={() => navigate('tracker')} />}
              {currentView.route === 'settings' && <Settings onSettingsUpdated={handleSettingsUpdated} initialTab="ai" />}
              {currentView.route === 'services' && <Settings onSettingsUpdated={handleSettingsUpdated} initialTab="services" />}
              {currentView.route === 'pricing' && <Settings onSettingsUpdated={handleSettingsUpdated} initialTab="pricing" />}
              {currentView.route === 'kb' && <KnowledgeBase />}
            </ErrorBoundary>
          </main>

          <footer className="bg-surface border-t border-border py-4 text-center text-xs text-ink-muted transition-colors">
            <p>© {new Date().getFullYear()} Another Marketing Agency — RFP Response Assistant</p>
          </footer>
        </div>
      </ConfirmProvider>
    </ToastProvider>
  );
}
