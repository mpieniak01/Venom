import type { ReactNode } from "react";
import { Button, type ButtonSize, type ButtonVariant } from "./button";

type IconButtonProps = {
  label: string;
  icon: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
  onClick?: () => void;
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
};

export function IconButton({
  label,
  icon,
  variant = "outline",
  size = "sm",
  className,
  type = "button",
  disabled,
  onClick,
}: IconButtonProps) {
  return (
    <Button
      aria-label={label}
      title={label}
      variant={variant}
      size={size}
      icon
      className={className}
      type={type}
      disabled={disabled}
      onClick={onClick}
    >
      {icon}
    </Button>
  );
}
