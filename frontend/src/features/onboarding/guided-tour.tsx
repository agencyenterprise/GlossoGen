"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";
import { ArrowLeft, ArrowRight, X } from "lucide-react";

/** One stop in a guided tour: a highlighted element plus explanatory copy. */
export interface TourStep {
  /** Element to spotlight, as either a ref or a getter resolved live each step
   *  (the getter form suits targets that mount asynchronously via ``onEnter``).
   *  Resolving to null renders a centered card with no spotlight. */
  target: RefObject<HTMLElement | null> | (() => HTMLElement | null);
  title: string;
  body: ReactNode;
  /** Side-effect run when the step becomes active (e.g. open a panel so its
   *  target is on screen). */
  onEnter?: () => void;
}

function resolveTargetEl(step: TourStep): HTMLElement | null {
  if (typeof step.target === "function") {
    return step.target();
  }
  return step.target.current;
}

interface TargetRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

const SPOTLIGHT_PADDING = 6;
const CARD_WIDTH = 340;
const CARD_GAP = 14;
const VIEWPORT_MARGIN = 12;

function readRect(element: HTMLElement | null): TargetRect | null {
  if (element === null) {
    return null;
  }
  const r = element.getBoundingClientRect();
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

function cardPosition(rect: TargetRect | null, cardHeight: number): { top: number; left: number } {
  const maxTop = window.innerHeight - cardHeight - VIEWPORT_MARGIN;
  if (rect === null) {
    return {
      top: Math.max(VIEWPORT_MARGIN, window.innerHeight / 2 - cardHeight / 2),
      left: Math.max(VIEWPORT_MARGIN, window.innerWidth / 2 - CARD_WIDTH / 2),
    };
  }
  const spaceBelow = window.innerHeight - (rect.top + rect.height);
  const placeBelow = spaceBelow >= cardHeight + CARD_GAP || spaceBelow >= rect.top;
  let top: number;
  if (placeBelow) {
    top = rect.top + rect.height + CARD_GAP;
  } else {
    top = rect.top - CARD_GAP - cardHeight;
  }
  top = Math.max(VIEWPORT_MARGIN, Math.min(top, maxTop));
  let left = rect.left;
  if (left + CARD_WIDTH > window.innerWidth - VIEWPORT_MARGIN) {
    left = window.innerWidth - VIEWPORT_MARGIN - CARD_WIDTH;
  }
  left = Math.max(VIEWPORT_MARGIN, left);
  return { top, left };
}

/**
 * A dismissible step-through overlay that dims the page, spotlights one element
 * at a time, and shows an explanatory callout beside it. Rendered into a portal
 * so it floats above the app. Generic: the caller supplies the steps.
 *
 * Mounted only while the tour is active (the caller conditionally renders it),
 * so each opening starts fresh at the first step.
 */
export function GuidedTour({ steps, onClose }: { steps: TourStep[]; onClose: () => void }) {
  const [stepIndex, setStepIndex] = useState(0);
  const [rect, setRect] = useState<TargetRect | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);

  const step = steps[stepIndex] ?? null;

  const recomputeRect = useCallback(() => {
    if (step === null) {
      setRect(null);
      return;
    }
    setRect(readRect(resolveTargetEl(step)));
  }, [step]);

  useLayoutEffect(() => {
    if (step === null) {
      return undefined;
    }
    step.onEnter?.();
    const target = resolveTargetEl(step);
    if (target !== null) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    const raf = requestAnimationFrame(recomputeRect);
    const timer = setTimeout(recomputeRect, 320);
    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(timer);
    };
  }, [step, recomputeRect]);

  useEffect(() => {
    if (step === null) {
      return undefined;
    }
    window.addEventListener("scroll", recomputeRect, true);
    window.addEventListener("resize", recomputeRect);
    return () => {
      window.removeEventListener("scroll", recomputeRect, true);
      window.removeEventListener("resize", recomputeRect);
    };
  }, [step, recomputeRect]);

  const isLast = stepIndex === steps.length - 1;
  const goNext = useCallback(() => {
    if (isLast) {
      onClose();
      return;
    }
    setStepIndex(index => Math.min(index + 1, steps.length - 1));
  }, [isLast, onClose, steps.length]);
  const goBack = useCallback(() => {
    setStepIndex(index => Math.max(index - 1, 0));
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      } else if (event.key === "ArrowRight") {
        goNext();
      } else if (event.key === "ArrowLeft") {
        goBack();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, goNext, goBack]);

  // Position the callout from its real measured height so it never spills off
  // screen; important when the target is a large centered element (the
  // round-timeline modal), which would otherwise push a fixed-estimate card
  // partly below the viewport.
  useLayoutEffect(() => {
    const card = cardRef.current;
    if (card === null) {
      return;
    }
    const position = cardPosition(rect, card.offsetHeight);
    card.style.top = `${position.top}px`;
    card.style.left = `${position.left}px`;
  }, [rect, stepIndex]);

  if (step === null || typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div
      className="fixed inset-0 z-100"
      role="dialog"
      aria-modal="true"
      aria-label="Interface tour"
    >
      {/* Full-screen click-catcher: advances the tour and freezes the app. */}
      <div
        className="absolute inset-0"
        style={rect === null ? { backgroundColor: "rgba(0, 0, 0, 0.55)" } : undefined}
        onClick={goNext}
      />

      {rect !== null ? (
        <div
          className="pointer-events-none absolute rounded-lg ring-2 ring-primary/70 transition-all duration-300"
          style={{
            top: rect.top - SPOTLIGHT_PADDING,
            left: rect.left - SPOTLIGHT_PADDING,
            width: rect.width + SPOTLIGHT_PADDING * 2,
            height: rect.height + SPOTLIGHT_PADDING * 2,
            boxShadow: "0 0 0 9999px rgba(0, 0, 0, 0.55)",
          }}
        />
      ) : null}

      <div
        ref={cardRef}
        className="absolute rounded-xl border border-border bg-background p-4 shadow-2xl"
        style={{ width: CARD_WIDTH }}
        onClick={event => event.stopPropagation()}
      >
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {stepIndex + 1} / {steps.length}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Skip tour"
            className="inline-flex items-center gap-1 rounded p-0.5 text-[12px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <h3 className="mb-1.5 text-sm font-semibold text-foreground">{step.title}</h3>
        <div className="mb-3 text-[13px] leading-relaxed text-muted-foreground">{step.body}</div>
        <div className="flex items-center justify-end gap-1.5">
          <button
            type="button"
            onClick={goBack}
            disabled={stepIndex === 0}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-[12px] text-muted-foreground transition-colors hover:bg-muted disabled:opacity-40"
          >
            <ArrowLeft className="h-3 w-3" /> Back
          </button>
          <button
            type="button"
            onClick={goNext}
            className="inline-flex items-center gap-1 rounded-md bg-primary px-2.5 py-1 text-[12px] font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {isLast ? "Done" : "Next"}
            {!isLast ? <ArrowRight className="h-3 w-3" /> : null}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
