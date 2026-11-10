"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { Loader2 } from "lucide-react";

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
type ButtonSize = "md" | "sm";

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  asChild?: boolean;
};

/** Primary action control. Pending state announces via aria-busy. */
export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  asChild = false,
  disabled,
  children,
  ...rest
}: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      className="hos-btn"
      data-variant={variant}
      data-size={size}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Loader2 size={16} aria-hidden="true" /> : null}
      {children}
    </Comp>
  );
}

export type IconButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
};

/** Icon-only button. Label is mandatory (no icon-only mystery buttons). */
export function IconButton({ label, children, ...rest }: IconButtonProps) {
  return (
    <button type="button" className="hos-icon-btn" aria-label={label} {...rest}>
      {children}
    </button>
  );
}
