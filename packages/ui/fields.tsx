"use client";

import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";

export function Label({
  htmlFor,
  required,
  children,
}: {
  htmlFor?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label htmlFor={htmlFor} className="hos-label">
      {children}
      {required ? (
        <span className="hos-required" aria-hidden="true">
          {" "}
          *
        </span>
      ) : null}
    </label>
  );
}

export function HelperText({ id, children }: { id?: string; children: React.ReactNode }) {
  return (
    <p id={id} className="hos-helper">
      {children}
    </p>
  );
}

/** Inline field error. Pair with aria-describedby + aria-invalid on inputs. */
export function ErrorMessage({ id, children }: { id?: string; children: React.ReactNode }) {
  return (
    <p id={id} role="alert" className="hos-error-text">
      {children}
    </p>
  );
}

export type FieldProps = {
  label: string;
  htmlFor: string;
  required?: boolean;
  description?: string;
  error?: string;
  children: (ids: { describedBy?: string }) => React.ReactNode;
};

/**
 * Accessible field wrapper: wires label, description, and error to the
 * control via aria-describedby. Error takes precedence in the description.
 */
export function Field({ label, htmlFor, required, description, error, children }: FieldProps) {
  const descId = description ? `${htmlFor}-description` : undefined;
  const errId = error ? `${htmlFor}-error` : undefined;
  const describedBy = [errId, descId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="hos-field">
      <Label htmlFor={htmlFor} required={required}>
        {label}
      </Label>
      {children({ describedBy })}
      {description && !error ? <HelperText id={descId}>{description}</HelperText> : null}
      {error ? <ErrorMessage id={errId}>{error}</ErrorMessage> : null}
    </div>
  );
}

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

export function Input({ ...rest }: InputProps) {
  return <input className="hos-input" {...rest} />;
}

export type TextareaProps = React.TextareaHTMLAttributes<HTMLTextAreaElement>;

export function Textarea({ ...rest }: TextareaProps) {
  return <textarea className="hos-textarea" {...rest} />;
}

export function Select({
  label,
  options,
  ...rest
}: {
  label?: string;
  options: Array<{ value: string; label: string }>;
} & React.SelectHTMLAttributes<HTMLSelectElement>) {
  // Native select: explicit <label htmlFor> is the accessible name when
  // rendered inside Field; `label` is a fallback aria-label otherwise.
  const ariaProps = label ? { "aria-label": rest["aria-label"] ?? label } : {};
  return (
    <select className="hos-input hos-select-trigger" {...ariaProps} {...rest}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/** Radix-powered select for custom-styled dropdowns. Native Select preferred for dense forms. */
export function RichSelect({
  label,
  value,
  onValueChange,
  options,
  placeholder,
  invalid,
  describedBy,
}: {
  label: string;
  value?: string;
  onValueChange?: (v: string) => void;
  options: Array<{ value: string; label: string }>;
  placeholder?: string;
  invalid?: boolean;
  describedBy?: string;
}) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange}>
      <SelectPrimitive.Trigger
        className="hos-input hos-select-trigger"
        aria-label={label}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon aria-hidden="true">
          <ChevronDown size={16} />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content className="hos-popover" position="popper">
          <SelectPrimitive.Viewport>
            {options.map((o) => (
              <SelectPrimitive.Item key={o.value} value={o.value} className="hos-menu-item">
                <SelectPrimitive.ItemText>{o.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator>
                  <Check size={16} aria-hidden="true" />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

export function Checkbox({
  label,
  ...rest
}: { label: React.ReactNode } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="hos-check-row">
      <input type="checkbox" {...rest} />
      <span>{label}</span>
    </label>
  );
}

export function Radio({
  label,
  ...rest
}: { label: React.ReactNode } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="hos-check-row">
      <input type="radio" {...rest} />
      <span>{label}</span>
    </label>
  );
}

export function Switch({
  label,
  ...rest
}: { label: React.ReactNode } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="hos-check-row">
      <input type="checkbox" role="switch" {...rest} />
      <span>{label}</span>
    </label>
  );
}
