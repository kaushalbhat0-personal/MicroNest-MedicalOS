import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Info,
  XCircle,
  type LucideIcon,
} from "lucide-react";

export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";

/**
 * Backend-authoritative status presentation. The frontend NEVER invents
 * business statuses: every backend status string maps to a fixed
 * (tone, label) pair. Unknown strings fail safe to neutral "Unknown".
 */
export type StatusPresentation = { tone: StatusTone; label: string };

const BACKEND_STATUS_MAP: Record<string, StatusPresentation> = {
  // appointments
  scheduled: { tone: "info", label: "Scheduled" },
  confirmed: { tone: "info", label: "Confirmed" },
  checked_in: { tone: "info", label: "Checked in" },
  completed: { tone: "success", label: "Completed" },
  cancelled: { tone: "neutral", label: "Cancelled" },
  no_show: { tone: "warning", label: "No-show" },
  // encounters / notes
  open: { tone: "info", label: "Open" },
  closed: { tone: "neutral", label: "Closed" },
  draft: { tone: "neutral", label: "Draft" },
  finalized: { tone: "success", label: "Finalized" },
  amended: { tone: "info", label: "Amended" },
  // prescriptions
  signed: { tone: "success", label: "Signed" },
  // invoices / credit notes
  issued: { tone: "info", label: "Issued" },
  partially_paid: { tone: "warning", label: "Partially paid" },
  paid: { tone: "success", label: "Paid" },
  voided: { tone: "neutral", label: "Void" },
  void: { tone: "neutral", label: "Void" },
  // payments
  recorded: { tone: "info", label: "Recorded" },
  partially_allocated: { tone: "warning", label: "Partially allocated" },
  allocated: { tone: "success", label: "Allocated" },
  partially_refunded: { tone: "warning", label: "Partially refunded" },
  refunded: { tone: "neutral", label: "Refunded" },
  // dental plans / items / procedures
  active: { tone: "info", label: "Active" },
  proposed: { tone: "neutral", label: "Proposed" },
  planned: { tone: "info", label: "Planned" },
  in_progress: { tone: "info", label: "In progress" },
  // consent
  pending: { tone: "warning", label: "Pending" },
  granted: { tone: "success", label: "Granted" },
  declined: { tone: "danger", label: "Declined" },
  withdrawn: { tone: "neutral", label: "Withdrawn" },
  // subscriptions (O1.3R read-only; backend-authoritative, unenforced)
  // NB: `cancelled` (neutral) and `expired` (neutral) already exist above
  // and are reused for subscriptions — no duplicate keys allowed here.
  trial: { tone: "info", label: "Trial" },
  past_due: { tone: "warning", label: "Past due" },
  grace: { tone: "warning", label: "Grace" },
  suspended: { tone: "danger", label: "Suspended" },
  // tenant lifecycle (platform console; neutral, never alarming on its own)
  deactivated: { tone: "neutral", label: "Deactivated" },
  // recalls / misc
  scheduled_recalls: { tone: "info", label: "Scheduled" },
  missed: { tone: "warning", label: "Missed" },
  partial: { tone: "warning", label: "Partial" },
  overdue: { tone: "danger", label: "Overdue" },
  expired: { tone: "neutral", label: "Expired" },
  converted: { tone: "success", label: "Converted" },
  approved: { tone: "success", label: "Approved" },
  rejected: { tone: "danger", label: "Rejected" },
  revoked: { tone: "neutral", label: "Revoked" },
  resolved: { tone: "success", label: "Resolved" },
  ruled_out: { tone: "neutral", label: "Ruled out" },
  superseded: { tone: "neutral", label: "Superseded" },
  current: { tone: "success", label: "Current" },
};

export function presentStatus(status: string): StatusPresentation {
  return BACKEND_STATUS_MAP[status] ?? { tone: "neutral", label: "Unknown" };
}

export const TONE_ICONS: Record<StatusTone, LucideIcon> = {
  success: CheckCircle2,
  warning: AlertCircle,
  danger: XCircle,
  info: Info,
  neutral: Clock,
};
