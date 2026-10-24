#!/usr/bin/env bash
# Theming lint gate: components must use semantic design tokens only.
# Fails if any `dark:` colour prefix, raw Tailwind palette colour, or legacy brand token appears in frontend/src.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0

check() {
  local label="$1" pattern="$2"
  local hits
  hits=$(grep -rnE "$pattern" frontend/src --include='*.jsx' --include='*.js' --include='*.css' || true)
  if [ -n "$hits" ]; then
    echo "✗ $label"
    echo "$hits" | head -20
    fail=1
  else
    echo "✓ $label"
  fi
}

check "no dark: colour prefixes"        'dark:(bg|text|border|ring|divide|fill|stroke)-'
check "no raw Tailwind palette colours" '\b(bg|text|border|ring|divide|fill|from|to)-(neutral|zinc|slate|gray|stone|amber|rose|red|emerald|green|sky|blue|purple|yellow|orange)-[0-9]{2,3}\b'
check "no sub-12px type"                'text-\[1[01]px\]'
check "no legacy/vendor brand tokens"   '\b(bg|text|border|ring|fill)-(brand|legacy)-'

exit $fail
