import { Brain } from "lucide-react";

import { SectionHeading } from "@/components/ui/section-heading";

type BrainHeaderProps = Readonly<{
  eyebrow: string;
  title: string;
  description: string;
}>;

export function BrainHeader({ eyebrow, title, description }: BrainHeaderProps) {
  return (
    <SectionHeading
      eyebrow={eyebrow}
      title={title}
      description={description}
      as="h1"
      size="lg"
      rightSlot={<Brain className="page-heading-icon" />}
    />
  );
}
