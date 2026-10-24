#!/usr/bin/env node
/**
 * Frontend Build & Syntax Validation Script
 * Hardened validation for offline/fallback environments without Vite.
 * Validates file existence, JavaScript module syntax, duplicate declarations/exports,
 * template literal termination, and native Node syntax on .js files.
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const FRONTEND_ROOT = path.resolve(__dirname, '..');

const REQUIRED_FILES = [
  'src/App.jsx',
  'src/main.jsx',
  'src/services/api.js',
  'src/components/Badge.jsx',
  'src/pages/RFPTracker.jsx',
  'src/pages/RFPDetail.jsx',
  'src/pages/NewRFP.jsx',
  'src/pages/KnowledgeBase.jsx',
  'src/pages/PricingAdmin.jsx',
  'src/pages/ServicesAdmin.jsx',
  'src/pages/Settings.jsx',
];

function validateSyntaxAndExports(relPath) {
  const fullPath = path.join(FRONTEND_ROOT, relPath);
  if (!fs.existsSync(fullPath)) {
    throw new Error(`Missing required file: ${relPath}`);
  }

  // 1. Native Node syntax check on plain JS files
  if (relPath.endsWith('.js')) {
    try {
      execFileSync(process.execPath, ['--check', fullPath], { stdio: 'pipe' });
    } catch (err) {
      const msg = err.stderr ? err.stderr.toString().trim() : err.message;
      throw new SyntaxError(`Native JS syntax check failed for ${relPath}: ${msg}`);
    }
  }

  const content = fs.readFileSync(fullPath, 'utf8');

  // 2. Duplicate Export Detection
  const exported = new Set();
  const duplicateExports = [];

  // Match: export function name, export async function name, export const name, export class name, etc.
  const declRegex = /export\s+(?:async\s+)?(?:function\*?|class|const|let|var)\s+([A-Za-z0-9_$]+)/g;
  let m;
  while ((m = declRegex.exec(content)) !== null) {
    const name = m[1];
    if (exported.has(name)) {
      duplicateExports.push(name);
    } else {
      exported.add(name);
    }
  }

  // Match: export { a, b, c as d }
  const listRegex = /export\s*\{([^}]+)\}/g;
  while ((m = listRegex.exec(content)) !== null) {
    const items = m[1].split(',');
    for (let item of items) {
      item = item.trim();
      if (!item) continue;
      const parts = item.split(/\s+as\s+/);
      const name = (parts[1] || parts[0]).trim();
      if (exported.has(name)) {
        duplicateExports.push(name);
      } else {
        exported.add(name);
      }
    }
  }

  if (duplicateExports.length > 0) {
    throw new SyntaxError(
      `Identifier '${duplicateExports[0]}' has already been declared (duplicate export in ${relPath})`
    );
  }

  // 3. Multiple default exports check
  const defaultMatches = content.match(/export\s+default\b/g);
  if (defaultMatches && defaultMatches.length > 1) {
    throw new SyntaxError(`Multiple export default statements found in ${relPath}`);
  }

  // 4. Duplicate top-level function declarations check (outside exports)
  const funcRegex = /^(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(/gm;
  const topFuncs = new Set();
  while ((m = funcRegex.exec(content)) !== null) {
    const name = m[1];
    if (topFuncs.has(name)) {
      throw new SyntaxError(`Identifier '${name}' has already been declared in ${relPath}`);
    }
    topFuncs.add(name);
  }

  // 5. Check balanced template literals (`...`)
  let backtickCount = 0;
  for (let i = 0; i < content.length; i++) {
    if (content[i] === '\\') {
      i++;
      continue;
    }
    if (content[i] === '`') {
      backtickCount++;
    }
  }
  if (backtickCount % 2 !== 0) {
    throw new SyntaxError(`Unclosed template literal (\`) in ${relPath}`);
  }

  console.log(`[OK] Verified syntax & exports: ${relPath}`);
}

function run() {
  console.log('[BUILD VALIDATION] Verifying frontend source files and syntax...');
  try {
    for (const file of REQUIRED_FILES) {
      validateSyntaxAndExports(file);
    }
    console.log('[BUILD SUCCESS] All frontend modules verified.');
    process.exit(0);
  } catch (err) {
    console.error(`[BUILD ERROR] ${err.message}`);
    process.exit(1);
  }
}

run();
