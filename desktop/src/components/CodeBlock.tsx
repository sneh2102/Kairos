// Snippet shown with a tech-stack question. Plain <pre>: no highlighter dependency for a few lines of code.
export default function CodeBlock({ code, language, className = "" }: { code: string; language?: string; className?: string }) {
  return (
    <div className={`rounded-xl border border-border bg-subtle text-left overflow-hidden ${className}`}>
      {language && (
        <div className="px-3 py-1.5 border-b border-border text-[11px] font-medium text-muted uppercase tracking-wide">
          {language}
        </div>
      )}
      <pre className="px-4 py-3 overflow-x-auto font-mono text-[13px] leading-relaxed text-fg">
        <code>{code}</code>
      </pre>
    </div>
  );
}
