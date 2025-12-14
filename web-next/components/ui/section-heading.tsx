import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

type SectionHeadingProps = {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  rightSlot?: ReactNode;
  className?: string;
  as?: "h1" | "h2" | "h3" | "h4";
  size?: "lg" | "md" | "sm";
};

const sizeMap: Record<NonNullable<SectionHeadingProps["size"]>, string> = {
  lg: "text-3xl",
  md: "text-2xl",
  sm: "text-xl",
};

export function SectionHeading({
  eyebrow,
  title,
  description,
  rightSlot,
  className,
  as = "h2",
  size = "md",
}: SectionHeadingProps) {
  const HeadingTag = as;
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-4", className)}>
      <div>
        {eyebrow && (
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">{eyebrow}</p>
        )}
        <HeadingTag className={cn("font-semibold text-white", sizeMap[size])}>{title}</HeadingTag>
        {description && <p className="mt-1 text-sm text-zinc-400">{description}</p>}
      </div>
      {rightSlot}
    </div>
  );
}
