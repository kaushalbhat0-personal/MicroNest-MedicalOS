import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/operations",
}));

vi.mock("@/lib/tenant", () => ({
  getSelectedTenant: () => "tenant-1",
}));

const apiGet = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    get: (...args: unknown[]) => apiGet(...args),
    post: vi.fn(),
  },
}));

vi.mock("../shell", () => ({
  Shell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import OperationsPage from "./page";

const emptyDash = {
  location_id: "loc-1",
  location_name: "Main Clinic",
  service_date: "2026-11-24",
  timezone: "Asia/Kolkata",
  appointments: {
    scheduled_today: 0,
    waiting: 0,
    checked_in: 0,
    in_consultation: 0,
    completed: 0,
    cancelled: 0,
    no_show: 0,
  },
  reception: {
    scheduled_today: 0,
    waiting: 0,
    checked_in: 0,
    in_consultation: 0,
    completed: 0,
    cancelled: 0,
    no_show: 0,
  },
  follow_ups: { due_today: 0, overdue: 0, upcoming: 0 },
  billing: {
    outstanding_invoice_count: 0,
    outstanding_amount: "0.00",
    currency: "INR",
    payments_today_count: 0,
    payments_today_amount: "0.00",
  },
  availability: { clinic_hours: [], practitioners: [] },
  todays_appointments: [],
  appointments_list: { total: 0, returned: 0, truncated: false, limit: 50 },
  sections_omitted: [],
  follow_up_day_basis: "location_service_day",
};

describe("OperationsPage", () => {
  beforeEach(() => {
    push.mockReset();
    apiGet.mockReset();
  });

  it("shows loading then empty clinic state", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.includes("/locations") && !path.includes("operations")) {
        return Promise.resolve([{ id: "loc-1", name: "Main Clinic" }]);
      }
      if (path.includes("operations-dashboard")) {
        return Promise.resolve(emptyDash);
      }
      return Promise.reject(new Error(`unexpected ${path}`));
    });
    render(<OperationsPage />);
    expect(screen.getByText(/loading operations/i)).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText(/no appointments for this day/i)).toBeTruthy();
    });
    expect(screen.getAllByText(/Asia\/Kolkata/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Main Clinic/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/999 fake/i)).toBeNull();
  });

  it("renders metrics, appointments, and navigation actions", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.includes("/locations") && !path.includes("operations")) {
        return Promise.resolve([{ id: "loc-1", name: "Main Clinic" }]);
      }
      if (path.includes("operations-dashboard")) {
        return Promise.resolve({
          ...emptyDash,
          appointments: { ...emptyDash.appointments!, scheduled_today: 2, waiting: 1, checked_in: 1 },
          reception: { ...emptyDash.reception!, waiting: 1, checked_in: 1 },
          follow_ups: { due_today: 3, overdue: 1, upcoming: 2 },
          billing: {
            outstanding_invoice_count: 4,
            outstanding_amount: "1250.50",
            currency: "INR",
            payments_today_count: 2,
            payments_today_amount: "500.00",
          },
          availability: {
            clinic_hours: [{ start_local: "09:00:00", end_local: "17:00:00" }],
            practitioners: [
              {
                practitioner_id: "p1",
                display_name: "Dr Ada",
                verification_status: "approved",
                staff_windows: ["09:00-13:00"],
              },
            ],
          },
          todays_appointments: [
            {
              id: "a1",
              start_at: "2026-11-24T04:30:00Z",
              status: "checked_in",
              patient_id: "pat-1",
              patient_display_name: "Pat One",
              practitioner_display_name: "Dr Ada",
              queue_token: 7,
              notes: null,
            },
          ],
        });
      }
      return Promise.reject(new Error(`unexpected ${path}`));
    });
    render(<OperationsPage />);
    await waitFor(() => expect(screen.getByText("Pat One")).toBeTruthy());
    expect(screen.getByText("Dr Ada")).toBeTruthy();
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText(/Outstanding invoices: 4/)).toBeTruthy();
    expect(screen.getByText(/1250\.50/)).toBeTruthy();
    expect(screen.getByText(/Due on service day/i)).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getAllByText(/location service day/i).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /open reception board/i }));
    expect(push).toHaveBeenCalledWith("/reception");
  });

  it("shows partial appointment list banner when truncated", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.includes("/locations") && !path.includes("operations")) {
        return Promise.resolve([{ id: "loc-1", name: "Main Clinic" }]);
      }
      if (path.includes("operations-dashboard")) {
        return Promise.resolve({
          ...emptyDash,
          appointments: { ...emptyDash.appointments!, scheduled_today: 80 },
          appointments_list: { total: 80, returned: 50, truncated: true, limit: 50 },
          todays_appointments: [
            {
              id: "a1",
              start_at: "2026-11-24T04:30:00Z",
              status: "scheduled",
              patient_id: "pat-1",
              patient_display_name: "Pat One",
              practitioner_display_name: "Dr Ada",
              queue_token: null,
              notes: null,
            },
          ],
        });
      }
      return Promise.reject(new Error(`unexpected ${path}`));
    });
    render(<OperationsPage />);
    await waitFor(() => expect(screen.getByText(/Partial list/i)).toBeTruthy());
    expect(screen.getByText(/Showing 50 of 80/i)).toBeTruthy();
  });

  it("shows API error and permission-denied states", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.includes("/locations") && !path.includes("operations")) {
        return Promise.resolve([{ id: "loc-1", name: "Main Clinic" }]);
      }
      const err = new Error("permission denied") as Error & { status: number };
      err.status = 403;
      return Promise.reject(err);
    });
    render(<OperationsPage />);
    await waitFor(() => {
      expect(screen.getByText(/permission denied/i)).toBeTruthy();
    });
  });

  it("hides omitted sections for restricted permissions", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.includes("/locations") && !path.includes("operations")) {
        return Promise.resolve([{ id: "loc-1", name: "Main Clinic" }]);
      }
      if (path.includes("operations-dashboard")) {
        return Promise.resolve({
          ...emptyDash,
          billing: null,
          follow_ups: null,
          sections_omitted: ["billing", "follow_ups"],
        });
      }
      return Promise.reject(new Error(`unexpected ${path}`));
    });
    render(<OperationsPage />);
    await waitFor(() => {
      expect(screen.getByText(/Hidden for your role: billing, follow_ups/i)).toBeTruthy();
    });
    expect(screen.queryByRole("heading", { name: /billing snapshot/i })).toBeNull();
    expect(screen.queryByRole("heading", { name: /^follow-ups$/i })).toBeNull();
  });

  it("applies location and date selection to the dashboard request", async () => {
    apiGet.mockImplementation((path: string) => {
      if (path.includes("/locations") && !path.includes("operations")) {
        return Promise.resolve([
          { id: "loc-1", name: "Main Clinic" },
          { id: "loc-2", name: "Branch" },
        ]);
      }
      if (path.includes("operations-dashboard")) {
        return Promise.resolve(emptyDash);
      }
      return Promise.reject(new Error(`unexpected ${path}`));
    });
    render(<OperationsPage />);
    await waitFor(() => expect(screen.getByLabelText(/^Location$/)).toBeTruthy());
    fireEvent.change(screen.getByLabelText(/^Location$/), { target: { value: "loc-2" } });
    fireEvent.change(screen.getByLabelText(/^Service day$/), {
      target: { value: "2026-11-20" },
    });
    await waitFor(() => {
      const calls = apiGet.mock.calls.map((c: unknown[]) => String(c[0]));
      expect(calls.some((p: string) => p.includes("/locations/loc-2/operations-dashboard"))).toBe(
        true,
      );
      expect(calls.some((p: string) => p.includes("day=2026-11-20"))).toBe(true);
    });
  });
});
