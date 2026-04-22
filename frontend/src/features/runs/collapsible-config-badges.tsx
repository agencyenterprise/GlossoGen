"use client";

import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

type Entry = readonly [string, unknown];

type Props = {
  entries: Entry[];
  renderBadge: (entry: Entry) => ReactNode;
  toggleClassName: string;
  containerClassName?: string;
};

export function CollapsibleConfigBadges({
  entries,
  renderBadge,
  toggleClassName,
  containerClassName,
}: Props) {
  const [collapsed, setCollapsed] = useState(true);
  const [visibleCount, setVisibleCount] = useState(entries.length);
  const [needsToggle, setNeedsToggle] = useState(false);
  const measureRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const el = measureRef.current;
    if (!el) return;

    const measure = () => {
      const children = Array.from(el.children) as HTMLElement[];
      if (children.length === 0) {
        setNeedsToggle(false);
        return;
      }
      const firstTop = children[0]!.offsetTop;
      const toggleIndex = children.length - 1;
      const toggleOnRow1 = children[toggleIndex]!.offsetTop === firstTop;

      let fittedBadges = 0;
      for (let i = 0; i < entries.length; i += 1) {
        if (children[i]!.offsetTop === firstTop) {
          fittedBadges += 1;
        } else {
          break;
        }
      }

      if (fittedBadges === entries.length && toggleOnRow1) {
        setNeedsToggle(false);
        setVisibleCount(entries.length);
      } else {
        setNeedsToggle(true);
        setVisibleCount(toggleOnRow1 ? fittedBadges : Math.max(0, fittedBadges - 1));
      }
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [entries]);

  const displayedEntries = collapsed && needsToggle ? entries.slice(0, visibleCount) : entries;

  return (
    <div className={`relative ${containerClassName ?? ""}`}>
      <div
        ref={measureRef}
        aria-hidden
        className="pointer-events-none invisible absolute inset-x-0 top-0 flex flex-wrap gap-1.5"
      >
        {entries.map(renderBadge)}
        <span className={toggleClassName}>...</span>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {displayedEntries.map(renderBadge)}
        {needsToggle ? (
          <button
            type="button"
            onClick={event => {
              event.stopPropagation();
              setCollapsed(value => !value);
            }}
            className={toggleClassName}
          >
            {collapsed ? "..." : "show less"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
