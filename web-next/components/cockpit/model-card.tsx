"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type ModelListItemProps = {
  name: string;
  sizeGb?: number | null;
  source?: string | null;
  active?: boolean;
  onActivate: () => void;
};

export function ModelListItem({ name, sizeGb, source, active, onActivate }: ModelListItemProps) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-4 text-sm text-white shadow-card">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-lg font-semibold">{name}</p>
          <p className="text-xs text-zinc-400">
            {sizeGb ? `${sizeGb} GB` : "Rozmiar —"}
            {source ? ` • ${source}` : ""}
          </p>
        </div>
        <Badge tone={active ? "success" : "neutral"}>
          {active ? "Aktywny" : "Gotowy"}
        </Badge>
      </div>
      <Button
        size="sm"
        variant={active ? "secondary" : "outline"}
        disabled={active}
        className="mt-4 rounded-full px-4"
        onClick={onActivate}
      >
        {active ? "Model aktywny" : "Ustaw jako aktywny"}
      </Button>
    </div>
  );
}

type RepoActionCardProps = {
  title: string;
  description: string;
  variant?: "primary" | "danger";
  onClick: () => void;
  pending?: boolean;
};

export function RepoActionCard({
  title,
  description,
  variant = "primary",
  onClick,
  pending,
}: RepoActionCardProps) {
  const gradient =
    variant === "danger"
      ? "from-rose-500/20 via-rose-500/10 to-transparent"
      : "from-emerald-500/30 via-emerald-500/10 to-transparent";

  const buttonVariant = variant === "danger" ? "danger" : "secondary";

  return (
    <div
      className={`rounded-3xl border border-white/10 bg-gradient-to-br ${gradient} p-4 text-white shadow-card`}
    >
      <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">{title}</p>
      <p className="mt-2 text-sm text-zinc-200">{description}</p>
      <Button
        className="mt-4 rounded-full px-4"
        variant={buttonVariant}
        size="sm"
        disabled={pending}
        onClick={onClick}
      >
        {pending ? "Wykonuję..." : "Uruchom"}
      </Button>
    </div>
  );
}
