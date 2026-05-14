"use client";

import { Users, ArrowLeftRight, UserPlus } from "lucide-react";
import type { ComponentType } from "react";
import type { ContainerYardMode } from "./container-yard-knobs-state";

type ModeCard = {
  mode: ContainerYardMode;
  title: string;
  description: string;
  icon: ComponentType<{ className: string }>;
};

const MODE_CARDS: ModeCard[] = [
  {
    mode: "single",
    title: "Single team",
    description: "One yard operator, logistics planner, and crane operator work all rounds.",
    icon: Users,
  },
  {
    mode: "swap",
    title: "Two-team swap",
    description: "Two parallel teams; crane operators swap between teams at a chosen round.",
    icon: ArrowLeftRight,
  },
  {
    mode: "intern",
    title: "Intern observer",
    description: "A silent intern joins, then replaces the crane operator mid-run.",
    icon: UserPlus,
  },
];

export function ContainerYardModeSelector({
  selected,
  onChange,
  disabled,
}: {
  selected: ContainerYardMode;
  onChange: (next: ContainerYardMode) => void;
  disabled: boolean;
}) {
  return (
    <div className="space-y-2">
      <span className="block text-sm font-medium">Execution mode</span>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {MODE_CARDS.map(card => {
          const Icon = card.icon;
          const isSelected = card.mode === selected;
          return (
            <button
              key={card.mode}
              type="button"
              onClick={() => onChange(card.mode)}
              disabled={disabled}
              className={`flex flex-col items-start gap-1.5 rounded-md border p-3 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                isSelected
                  ? "border-primary bg-primary/5 ring-2 ring-primary/30"
                  : "border-border bg-background hover:border-primary/50 hover:bg-muted/30"
              }`}
            >
              <div className="flex items-center gap-2">
                <Icon
                  className={`h-4 w-4 ${isSelected ? "text-primary" : "text-muted-foreground"}`}
                />
                <span className="text-sm font-medium">{card.title}</span>
              </div>
              <p className="text-xs text-muted-foreground">{card.description}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}
