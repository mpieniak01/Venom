"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { forwardRef } from "react";

const ConfirmDialog = DialogPrimitive.Root;
const ConfirmDialogTrigger = DialogPrimitive.Trigger;
const ConfirmDialogPortal = DialogPrimitive.Portal;

const ConfirmDialogOverlay = forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/60 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in",
      className,
    )}
    {...props}
  />
));
ConfirmDialogOverlay.displayName = DialogPrimitive.Overlay.displayName;

const ConfirmDialogContent = forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <ConfirmDialogPortal>
    <ConfirmDialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 border border-white/10 bg-zinc-950/95 p-6 shadow-2xl rounded-2xl",
        "data-[state=open]:animate-in data-[state=closed]:animate-out",
        "data-[state=closed]:fade-out data-[state=open]:fade-in",
        "data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
        className,
      )}
      {...props}
    >
      {children}
    </DialogPrimitive.Content>
  </ConfirmDialogPortal>
));
ConfirmDialogContent.displayName = DialogPrimitive.Content.displayName;

const ConfirmDialogTitle = forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("text-lg font-semibold text-white mb-2", className)}
    {...props}
  />
));
ConfirmDialogTitle.displayName = DialogPrimitive.Title.displayName;

const ConfirmDialogDescription = forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-zinc-400 mb-4", className)}
    {...props}
  />
));
ConfirmDialogDescription.displayName = DialogPrimitive.Description.displayName;

interface ConfirmDialogActionsProps {
  onConfirm: () => void;
  onCancel: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmVariant?: "primary" | "danger" | "secondary";
}

function ConfirmDialogActions({
  onConfirm,
  onCancel,
  confirmLabel = "Potwierdź",
  cancelLabel = "Anuluj",
  confirmVariant = "danger",
}: ConfirmDialogActionsProps) {
  return (
    <div className="flex justify-end gap-3 mt-6">
      <DialogPrimitive.Close asChild>
        <Button variant="ghost" onClick={onCancel}>
          {cancelLabel}
        </Button>
      </DialogPrimitive.Close>
      <DialogPrimitive.Close asChild>
        <Button variant={confirmVariant} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </DialogPrimitive.Close>
    </div>
  );
}

export {
  ConfirmDialog,
  ConfirmDialogTrigger,
  ConfirmDialogContent,
  ConfirmDialogTitle,
  ConfirmDialogDescription,
  ConfirmDialogActions,
};
