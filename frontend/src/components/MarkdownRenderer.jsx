import React from 'react';
import { Bold, Italic, Quote, Table as TableIcon, Eye, Code } from 'lucide-react';

/** Parses markdown inline styles (bold, italic, code) */
function renderInline(text) {
  if (!text) return null;

  const parts = [];
  let keyIdx = 0;
  const tokenRegex = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match;

  while ((match = tokenRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.substring(lastIndex, match.index));
    }
    const token = match[0];
    if (token.startsWith('**') && token.endsWith('**')) {
      parts.push(
        <strong key={keyIdx++} className="font-bold text-ink">
          {token.slice(2, -2)}
        </strong>
      );
    } else if (token.startsWith('*') && token.endsWith('*')) {
      parts.push(
        <em key={keyIdx++} className="italic">
          {token.slice(1, -1)}
        </em>
      );
    } else if (token.startsWith('`') && token.endsWith('`')) {
      parts.push(
        <code key={keyIdx++} className="px-1.5 py-0.5 rounded bg-surface-raised text-xs font-mono text-ink">
          {token.slice(1, -1)}
        </code>
      );
    }
    lastIndex = tokenRegex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push(text.substring(lastIndex));
  }

  return parts.length > 0 ? parts : text;
}

/** Rich Markdown renderer: headings, bold, italics, code, blockquotes, lists, tables */
export function MarkdownRenderer({ content, className = '' }) {
  if (!content) {
    return <p className="text-ink-muted italic text-sm">No content drafted yet.</p>;
  }

  const rawLines = content.split(/\r?\n/);
  const elements = [];
  let tableBuffer = [];
  let blockquoteBuffer = [];
  let listBuffer = [];
  let elKey = 0;

  function flushTable() {
    if (tableBuffer.length === 0) return;
    const rows = tableBuffer.map((row) =>
      row
        .split('|')
        .map((cell) => cell.trim())
        .filter((_, idx, arr) => idx > 0 && idx < arr.length - 1)
    );

    if (rows.length > 0) {
      const headerRow = rows[0];
      const hasDivider = rows.length > 1 && rows[1].every((c) => /^:?-+:?$/.test(c));
      const bodyRows = hasDivider ? rows.slice(2) : rows.slice(1);

      elements.push(
        <div key={`table-${elKey++}`} className="my-4 overflow-x-auto border border-border-strong rounded-lg">
          <table className="w-full text-left text-sm border-collapse">
            <thead className="bg-surface-raised border-b border-border-strong text-xs uppercase font-bold text-ink">
              <tr>
                {headerRow.map((cell, cIdx) => (
                  <th key={cIdx} scope="col" className="px-4 py-2.5 border-r border-border last:border-r-0">
                    {renderInline(cell)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-surface">
              {bodyRows.map((row, rIdx) => (
                <tr key={rIdx} className="hover:bg-surface-raised/60">
                  {row.map((cell, cIdx) => (
                    <td key={cIdx} className="px-4 py-2.5 border-r border-border last:border-r-0 text-ink">
                      {renderInline(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    tableBuffer = [];
  }

  function flushBlockquote() {
    if (blockquoteBuffer.length === 0) return;
    elements.push(
      <blockquote
        key={`bq-${elKey++}`}
        className="border-l-4 border-accent bg-surface-raised px-4 py-2 my-3 rounded-r italic text-ink text-sm leading-relaxed"
      >
        {blockquoteBuffer.map((line, idx) => (
          <p key={idx} className={idx > 0 ? 'mt-1.5' : ''}>
            {renderInline(line)}
          </p>
        ))}
      </blockquote>
    );
    blockquoteBuffer = [];
  }

  function flushList() {
    if (listBuffer.length === 0) return;
    elements.push(
      <ul key={`list-${elKey++}`} className="list-disc list-inside space-y-1 my-2.5 pl-2 text-sm text-ink">
        {listBuffer.map((item, idx) => (
          <li key={idx} className="leading-relaxed">
            {renderInline(item)}
          </li>
        ))}
      </ul>
    );
    listBuffer = [];
  }

  for (let i = 0; i < rawLines.length; i++) {
    const trimmed = rawLines[i].trim();

    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      flushBlockquote();
      flushList();
      tableBuffer.push(trimmed);
      continue;
    }
    flushTable();

    if (trimmed.startsWith('>')) {
      flushList();
      blockquoteBuffer.push(trimmed.replace(/^>\s*/, ''));
      continue;
    }
    flushBlockquote();

    if (/^[-*]\s+/.test(trimmed)) {
      listBuffer.push(trimmed.replace(/^[-*]\s+/, ''));
      continue;
    }
    flushList();

    if (!trimmed) continue;

    if (trimmed.startsWith('#### ')) {
      elements.push(
        <h4 key={`h4-${elKey++}`} className="text-base font-bold text-ink mt-4 mb-1.5 tracking-tight">
          {renderInline(trimmed.replace(/^####\s+/, ''))}
        </h4>
      );
      continue;
    }
    if (trimmed.startsWith('### ')) {
      elements.push(
        <h3 key={`h3-${elKey++}`} className="text-lg font-bold text-ink mt-5 mb-2 tracking-tight">
          {renderInline(trimmed.replace(/^###\s+/, ''))}
        </h3>
      );
      continue;
    }
    if (trimmed.startsWith('## ')) {
      elements.push(
        <h2 key={`h2-${elKey++}`} className="text-xl font-bold text-ink mt-6 mb-2.5 border-b border-border pb-1 tracking-tight">
          {renderInline(trimmed.replace(/^##\s+/, ''))}
        </h2>
      );
      continue;
    }
    if (trimmed.startsWith('# ')) {
      elements.push(
        <h1 key={`h1-${elKey++}`} className="text-2xl font-bold text-ink mt-6 mb-3 tracking-tight">
          {renderInline(trimmed.replace(/^#\s+/, ''))}
        </h1>
      );
      continue;
    }

    elements.push(
      <p key={`p-${elKey++}`} className="mb-3 text-sm text-ink leading-relaxed">
        {renderInline(trimmed)}
      </p>
    );
  }

  flushTable();
  flushBlockquote();
  flushList();

  return <div className={`max-w-none ${className}`}>{elements}</div>;
}

const TOOL_BTN = 'px-1.5 py-1 min-w-[2rem] rounded text-xs font-bold text-ink hover:bg-surface transition-colors';

/** Editor toolbar: headings, inline formatting, quotes, tables, preview toggle */
export function MarkdownToolbar({ onInsert, isPreview, onTogglePreview }) {
  return (
    <div
      role="toolbar"
      aria-label="Markdown formatting"
      className="flex flex-wrap items-center justify-between gap-1 p-1.5 bg-surface-raised border border-border-strong rounded-t-md text-ink"
    >
      <div className="flex items-center gap-1 flex-wrap">
        <button type="button" onClick={() => onInsert('h2')} aria-label="Insert heading 2" title="Heading 2 (##)" className={TOOL_BTN}>
          H2
        </button>
        <button type="button" onClick={() => onInsert('h3')} aria-label="Insert heading 3" title="Heading 3 (###)" className={TOOL_BTN}>
          H3
        </button>
        <button type="button" onClick={() => onInsert('h4')} aria-label="Insert heading 4" title="Heading 4 (####)" className={TOOL_BTN}>
          H4
        </button>

        <span className="w-px h-4 bg-border-strong mx-1" aria-hidden="true" />

        <button type="button" onClick={() => onInsert('bold')} aria-label="Bold" title="Bold (**text**)" className={TOOL_BTN}>
          <Bold className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
        <button type="button" onClick={() => onInsert('italic')} aria-label="Italic" title="Italic (*text*)" className={TOOL_BTN}>
          <Italic className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
        <button type="button" onClick={() => onInsert('quote')} aria-label="Blockquote" title="Quote (> text)" className={TOOL_BTN}>
          <Quote className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => onInsert('table')}
          aria-label="Insert table"
          title="Insert table"
          className={`${TOOL_BTN} inline-flex items-center gap-1 font-medium`}
        >
          <TableIcon className="w-3.5 h-3.5" aria-hidden="true" />
          <span>Table</span>
        </button>
      </div>

      <button
        type="button"
        onClick={onTogglePreview}
        aria-pressed={isPreview}
        className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold transition-colors ${
          isPreview ? 'bg-ink text-ink-inverse' : 'bg-surface text-ink border border-border-strong hover:bg-surface-raised'
        }`}
      >
        {isPreview ? <Code className="w-3 h-3" aria-hidden="true" /> : <Eye className="w-3 h-3" aria-hidden="true" />}
        <span>{isPreview ? 'Edit raw' : 'Preview'}</span>
      </button>
    </div>
  );
}

export default MarkdownRenderer;
