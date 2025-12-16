import type { ReactNode } from "react";
import { Button, type ButtonSize, type ButtonVariant } from "./button";

type IconButtonProps = {
  label: string;
  icon?: ReactNode;
  children?: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  onClick?: () => void;
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
  asChild?: boolean;
  dataTestId?: string;
};

export function IconButton({
  label,
  icon,
  children,
  variant = "outline",
  size = "sm",
  className,
  type = "button",
  disabled,
  asChild = false,
  onClick,
  dataTestId,
}: IconButtonProps) {
  const content = asChild && children ? children : icon;

  return (
    <Button
      data-testid={dataTestId}
      aria-label={label}
      title={label}
      variant={variant}
      size={size}
      icon={!asChild}
      className={className}
      type={type}
      disabled={disabled}
      asChild={asChild}
      onClick={onClick}
    >
      {content}
    </Button>
  );
}
