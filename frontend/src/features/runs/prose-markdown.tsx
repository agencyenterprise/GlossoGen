"use client";

import Markdown from "react-markdown";
import { cn } from "@/shared/lib/cn";

const BASE_PROSE =
  "prose prose-xs max-w-none text-xs leading-relaxed text-muted-foreground [&_strong]:text-foreground [&_ul]:ml-4 [&_ul]:list-disc [&_ol]:ml-4 [&_ol]:list-decimal [&_p]:my-1 [&_li]:my-0.5 [&_h1]:text-sm [&_h2]:text-sm [&_h3]:text-xs [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-medium [&_h1]:text-foreground [&_h2]:text-foreground [&_h3]:text-foreground";

export function ProseMarkdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn(BASE_PROSE, className)}>
      <Markdown>{children}</Markdown>
    </div>
  );
}
