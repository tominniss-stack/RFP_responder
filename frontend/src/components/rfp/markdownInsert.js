/** Markdown snippets inserted by editor toolbars. */
const SNIPPETS = {
  h2: '\n\n## Section heading\n',
  h3: '\n\n### Sub-heading\n',
  h4: '\n\n#### Minor heading\n',
  bold: ' **bold text** ',
  italic: ' *italic text* ',
  quote: '\n\n> "Client requirement or key emphasis…"\n',
  table:
    '\n\n| Deliverable | Description | Owner | Timeline |\n| :--- | :--- | :--- | :--- |\n| Discovery | Technical scoping & design system | Lead architect | Weeks 1–2 |\n| Build | Core platform implementation | Senior engineer | Weeks 3–6 |\n',
};

export function appendMarkdown(current, syntaxType) {
  const insertion = SNIPPETS[syntaxType] || '';
  return (current || '').trimEnd() + insertion;
}

export function sortSections(sections = []) {
  return [...sections].sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
}
