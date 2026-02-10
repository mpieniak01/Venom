import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

type SectionHeadingProps = Readonly<{
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  rightSlot?: ReactNode;
  className?: string;
  as?: "h1" | "h2" | "h3" | "h4";
  size?: "lg" | "md" | "sm";
}>;

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
  const trimmedEyebrow = eyebrow?.trim();
  let normalizedEyebrow: string | null = null;
  if (trimmedEyebrow) {
    normalizedEyebrow = trimmedEyebrow.startsWith("//")
      ? trimmedEyebrow
      : `// ${trimmedEyebrow}`;
  }
  return (
    <div className={cn("page-heading flex flex-wrap items-start justify-between gap-4", className)}>
      <div>
        {normalizedEyebrow && <p className="page-heading-eyebrow">{normalizedEyebrow}</p>}
        <HeadingTag className={cn("page-heading-title font-sans", sizeMap[size])}>{title}</HeadingTag>
        {description && <p className="page-heading-desc">{description}</p>}
      </div>
      {rightSlot}
    </div>
  );
}
