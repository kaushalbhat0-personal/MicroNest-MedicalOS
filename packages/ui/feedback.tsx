"use client";

import * as React from "react";
import { Button } from "./Button";
import { TONE_ICONS, presentStatus, type StatusTone } from "./status";

export function Badge({
  tone,
  icon,
  children,
}: {
  tone: StatusTone;
  icon?: boolean;
  children: React.ReactNode;
}) {
  const Icon = TONE_ICONS[tone];
  return (
    <span className="hos-badge" data-tone={tone}>
      {icon ? <Icon size={13} aria-hidden="true" /> : null}
      {children}
    </span>
  );
}

/**
 * Backend status chip. Always pairs color with a text label; callers pass
 * the raw backend status string - never a frontend-invented state.
 */
export function Status({ value, icon = true }: { value: string; icon?: boolean }) {
  const { tone, label } = presentStatus(value);
  return (
    <Badge tone={tone} icon={icon}>
      {label}
    </Badge>
  );
}

export function Alert({
  tone,
  title,
  children,
}: {
  tone: StatusTone;
  title?: string;
  children: React.ReactNode;
}) {
  const Icon = TONE_ICONS[tone];
  return (
    <div className="hos-alert" data-tone={tone} role="alert">
      <Icon size={18} aria-hidden="true" />
      <div>
        {title ? <strong>{title}</strong> : null}
        <div>{children}</div>
      </div>
    </div>
  );
}

export function Card({
  title,
  headingLevel = 2,
  children,
  actions,
}: {
  title?: string;
  headingLevel?: 1 | 2;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  const Heading = headingLevel === 1 ? "h1" : "h2";
  return (
    <section className="hos-card" aria-label={title}>
      {title ? <Heading>{title}</Heading> : null}
      {children}
      {actions}
    </section>
  );
}

export function Skeleton({ label = "Loading" }: { label?: string }) {
  return <div className="hos-skeleton" role="status" aria-label={label} />;
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return <div className="hos-spinner" role="status" aria-label={label} />;
}

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="hos-state">
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  children,
  onRetry,
  retryLabel = "Try again",
}: {
  title?: string;
  children?: React.ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
}) {
  return (
    <div className="hos-state" role="alert">
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
      {onRetry ? (
        <p>
          <Button type="button" variant="secondary" onClick={onRetry}>
            {retryLabel}
          </Button>
        </p>
      ) : null}
    </div>
  );
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="hos-state" role="status" aria-live="polite" aria-busy="true">
      <Spinner label={label} />
      <p>{label}...</p>
    </div>
  );
}
