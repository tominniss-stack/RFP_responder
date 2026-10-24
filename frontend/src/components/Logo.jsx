import React from 'react';

/**
 * Inline brand mark for Another Marketing Agency.
 * Pure SVG using currentColor / theme tokens so it re-themes with no asset swap.
 */
export default function Logo({ className = 'h-8 w-8', title = 'Another Marketing Agency' }) {
  return (
    <svg
      viewBox="0 0 40 40"
      role="img"
      aria-label={title}
      className={className}
      xmlns="http://www.w3.org/2000/svg"
    >
      <title>{title}</title>
      <rect x="2" y="2" width="36" height="36" rx="8" className="fill-accent" />
      {/* Three ascending bars — "another" step up */}
      <rect x="10" y="22" width="5" height="8" rx="1" className="fill-accent-ink" />
      <rect x="17.5" y="16" width="5" height="14" rx="1" className="fill-accent-ink" />
      <rect x="25" y="10" width="5" height="20" rx="1" className="fill-accent-ink" />
    </svg>
  );
}
