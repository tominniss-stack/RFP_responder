import React from 'react';
import { FileText, BookOpen, PlusCircle, Settings as SettingsIcon, Sun, Moon } from 'lucide-react';
import Logo from './Logo';

export default function Navbar({ activeTab, onSelectTab, apiConnected, mockExportActive, isDark, onToggleDark }) {
  const navItems = [
    { id: 'tracker', label: 'RFP Tracker', icon: FileText, href: '#/' },
    { id: 'new-rfp', label: 'New RFP', icon: PlusCircle, href: '#/new-rfp' },
    { id: 'kb', label: 'Knowledge Base', icon: BookOpen, href: '#/kb' },
    { id: 'settings', label: 'Settings', icon: SettingsIcon, href: '#/settings' },
  ];

  return (
    <header className="bg-surface border-b border-border sticky top-0 z-30 transition-colors">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 gap-4">
          {/* Brand */}
          <a
            href="#/"
            className="flex items-center gap-3 rounded-md"
            onClick={(e) => {
              e.preventDefault();
              onSelectTab('tracker');
            }}
          >
            <Logo className="h-8 w-8" />
            <span className="hidden sm:block leading-tight">
              <span className="font-bold text-sm tracking-tight text-ink block">Another Marketing Agency</span>
              <span className="text-xs font-medium text-ink-muted tracking-wide uppercase">RFP Response Assistant</span>
            </span>
          </a>

          {/* Primary navigation */}
          <nav aria-label="Primary" className="flex gap-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <a
                  key={item.id}
                  href={item.href}
                  onClick={(e) => {
                    e.preventDefault();
                    onSelectTab(item.id);
                  }}
                  aria-current={isActive ? 'page' : undefined}
                  className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
                    isActive ? 'bg-accent text-accent-ink font-semibold' : 'text-ink-muted hover:text-ink hover:bg-surface-raised font-medium'
                  }`}
                >
                  <Icon className="w-4 h-4" aria-hidden="true" />
                  <span className="hidden md:inline">{item.label}</span>
                  <span className="sr-only md:hidden">{item.label}</span>
                </a>
              );
            })}
          </nav>

          {/* Status + theme */}
          <div className="flex items-center gap-3">
            {mockExportActive && (
              <span className="hidden lg:inline-flex chip chip-neutral">Mock export mode</span>
            )}

            <span className="flex items-center gap-1.5 text-xs" role="status">
              <span
                className={`w-2 h-2 rounded-full ${apiConnected ? 'bg-success motion-safe:animate-pulse' : 'bg-warning'}`}
                aria-hidden="true"
              />
              <span className="font-medium text-ink-muted">{apiConnected ? 'API live' : 'Connecting…'}</span>
            </span>

            <button
              type="button"
              onClick={onToggleDark}
              className="btn-icon border border-border-strong"
              aria-pressed={isDark}
              aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
              title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {isDark ? <Sun className="w-4 h-4" aria-hidden="true" /> : <Moon className="w-4 h-4" aria-hidden="true" />}
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
