/** @type {import('tailwindcss').Config} */

/**
 * Design tokens are defined once as RGB-triplet CSS custom properties in
 * src/index.css (`:root` for light, `.dark` for dark). Tailwind utilities below
 * reference those variables, so every `bg-surface` / `text-ink` / `border-border`
 * utility automatically re-themes when the `dark` class is toggled on <html>.
 *
 * Rule: components use ONLY these semantic tokens — never raw palette colours
 * (neutral-500, amber-100, …) and never `dark:` colour prefixes.
 */
const token = (name) => `rgb(var(--color-${name}) / <alpha-value>)`;

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surfaces
        canvas: token('canvas'),
        surface: token('surface'),
        'surface-raised': token('surface-raised'),
        overlay: token('overlay'),

        // Text
        ink: token('ink'),
        'ink-muted': token('ink-muted'),
        'ink-inverse': token('ink-inverse'),

        // Borders
        border: token('border'),
        'border-strong': token('border-strong'),

        // Brand accent
        accent: token('accent'),
        'accent-hover': token('accent-hover'),
        'accent-ink': token('accent-ink'),
        'accent-soft': token('accent-soft'),

        // Semantic
        success: token('success'),
        'success-soft': token('success-soft'),
        warning: token('warning'),
        'warning-soft': token('warning-soft'),
        danger: token('danger'),
        'danger-soft': token('danger-soft'),
        info: token('info'),
        'info-soft': token('info-soft'),
      },
      ringOffsetColor: {
        canvas: 'rgb(var(--color-canvas))',
        surface: 'rgb(var(--color-surface))',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        raised: 'var(--shadow-raised)',
        sharp: 'var(--shadow-sharp)',
        'sharp-sm': 'var(--shadow-sharp-sm)',
      },
    },
  },
  plugins: [],
};
