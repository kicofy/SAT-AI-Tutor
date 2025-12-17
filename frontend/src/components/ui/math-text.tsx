"use client";

import clsx from "clsx";
import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

type MathTextProps = {
  text?: string | null;
  className?: string;
};

/**
 * Render Markdown with LaTeX support (KaTeX) while keeping a safe subset (no raw HTML).
 * Good for AI explanations that may include `$...$` or `$$...$$` math.
 */
export function MathText({ text, className }: MathTextProps) {
  const content = text?.trim();
  if (!content) return null;

  return (
    <div
      className={clsx(
        "math-text prose prose-invert prose-sm max-w-none leading-relaxed text-white/80",
        "whitespace-pre-wrap break-words",
        "overflow-x-auto",
        className
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
        skipHtml
        components={{
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
          ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          code: ({ children }) => (
            <code className="rounded bg-white/10 px-1 py-0.5 text-[0.95em]">{children}</code>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

