"use client";

import * as SheetPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { forwardRef, useRef } from "react";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const Sheet = SheetPrimitive.Root;
const SheetTrigger = SheetPrimitive.Trigger;
const SheetClose = SheetPrimitive.Close;

const SheetPortal = SheetPrimitive.Portal;
const SheetOverlay = forwardRef<
  React.ElementRef<typeof SheetPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof SheetPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <SheetPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in duration-500 ease-in-out",
      className,
    )}
    {...props}
  />
));
SheetOverlay.displayName = SheetPrimitive.Overlay.displayName;

type SheetContentProps = React.ComponentPropsWithoutRef<typeof SheetPrimitive.Content> & {
  returnFocusRef?: React.RefObject<HTMLElement | null>;
};

const SheetContent = forwardRef<
  React.ElementRef<typeof SheetPrimitive.Content>,
  SheetContentProps
>(({ className, children, onOpenAutoFocus, onCloseAutoFocus, returnFocusRef, ...props }, ref) => {
  const capturedFocusRef = useRef<HTMLElement | null>(null);
  const t = useTranslation();
  return (
    <SheetPortal>
      <SheetOverlay />
      <SheetPrimitive.Content
        ref={ref}
        className={cn(
          "fixed inset-y-0 right-0 z-50 w-full max-w-md border-l border-white/10 bg-zinc-950/95 p-6 shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right duration-500 ease-in-out",
          className,
        )}
        onOpenAutoFocus={(event) => {
          // Controlled/lazy sheets may be opened without a Radix Trigger. Save
          // the invoking control before FocusScope moves focus into the panel.
          const active = document.activeElement;
          capturedFocusRef.current = active instanceof HTMLElement && active !== document.body
            ? active
            : null;
          onOpenAutoFocus?.(event);
        }}
        onCloseAutoFocus={(event) => {
          onCloseAutoFocus?.(event);
          if (event.defaultPrevented) return;
          // A lazy panel can blur its trigger before FocusScope mounts. Prefer
          // the explicit external trigger when the owner provides one.
          const opener = returnFocusRef?.current ?? capturedFocusRef.current;
          if (opener?.isConnected && !opener.hasAttribute("disabled")) {
            event.preventDefault();
            opener.focus();
          }
        }}
        {...props}
      >
        <SheetPrimitive.Close
          aria-label={t("common.close")}
          className="absolute right-6 top-4 rounded text-zinc-400 transition hover:text-white"
        >
          <X className="h-4 w-4" />
        </SheetPrimitive.Close>
        {children}
      </SheetPrimitive.Content>
    </SheetPortal>
  );
});
SheetContent.displayName = SheetPrimitive.Content.displayName;

const SheetHeader = ({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) => <div className={cn("mb-4 space-y-2 text-left", className)}>{children}</div>;

const SheetTitle = ({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) => (
  <SheetPrimitive.Title asChild>
    <h3 className={cn("heading-h3", className)}>{children}</h3>
  </SheetPrimitive.Title>
);

const SheetDescription = ({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) => (
  <SheetPrimitive.Description asChild>
    <p className={cn("text-sm text-muted", className)}>{children}</p>
  </SheetPrimitive.Description>
);

export {
  Sheet,
  SheetTrigger,
  SheetClose,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
};
