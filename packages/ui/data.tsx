"use client";

import * as React from "react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type RowData,
} from "@tanstack/react-table";
import { ChevronRight } from "lucide-react";
import { Button } from "./Button";
import { EmptyState } from "./feedback";

export function Table({
  caption,
  columns,
  children,
  density,
}: {
  caption?: string;
  columns: React.ReactNode;
  children: React.ReactNode;
  density?: "comfortable" | "compact" | "clinical-dense";
}) {
  return (
    <div className="hos-table-wrap" data-density={density}>
      <table className="hos-table">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>{columns}</tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

/** Screen-reader-only helper (no global CSS dependency). */
export function srOnlyStyle(): React.CSSProperties {
  return {
    position: "absolute",
    width: 1,
    height: 1,
    padding: 0,
    margin: -1,
    overflow: "hidden",
    clip: "rect(0, 0, 0, 0)",
    whiteSpace: "nowrap",
    border: 0,
  };
}

export function Th({
  numeric,
  scope = "col",
  children,
}: {
  numeric?: boolean;
  scope?: "col" | "row";
  children: React.ReactNode;
}) {
  return (
    <th scope={scope} className={numeric ? "hos-num" : undefined}>
      {children}
    </th>
  );
}

export function Td({ numeric, children }: { numeric?: boolean; children: React.ReactNode }) {
  return <td className={numeric ? "hos-num" : undefined}>{children}</td>;
}

export type DataTableProps<T> = {
  columns: ColumnDef<T, unknown>[];
  data: T[];
  caption: string;
  emptyTitle: string;
  emptyHint?: string;
  emptyAction?: React.ReactNode;
  density?: "comfortable" | "compact" | "clinical-dense";
};

/**
 * TanStack-powered table for server-shaped lists (charge master,
 * appointment/encounter queues, audit). Sorting/filtering/pagination are
 * presentation-only unless the caller wires server params. Always supplies
 * caption + empty state; numeric alignment via column meta.
 */
export function DataTable<T>({
  columns,
  data,
  caption,
  emptyTitle,
  emptyHint,
  emptyAction,
  density = "compact",
}: DataTableProps<T>) {
  const table = useReactTable({
    columns,
    data,
    getCoreRowModel: getCoreRowModel(),
  });
  if (data.length === 0) {
    return <EmptyState title={emptyTitle} action={emptyAction}>{emptyHint}</EmptyState>;
  }
  return (
    <div className="hos-table-wrap" data-density={density}>
      <table className="hos-table">
        <caption style={srOnlyStyle()}>{caption}</caption>
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th
                  key={h.id}
                  scope="col"
                  className={h.column.columnDef.meta?.numeric ? "hos-num" : undefined}
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <td
                  key={cell.id}
                  className={cell.column.columnDef.meta?.numeric ? "hos-num" : undefined}
                >
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData extends RowData, TValue> {
    numeric?: boolean;
  }
}

export function Pagination({
  label,
  hasMore,
  onMore,
  pending,
}: {
  label: string;
  hasMore: boolean;
  onMore: () => void;
  pending?: boolean;
}) {
  return (
    <nav className="hos-pagination" aria-label="Pagination">
      <span>{label}</span>
      {hasMore ? (
        <Button variant="secondary" size="sm" onClick={onMore} loading={pending}>
          <ChevronRight size={16} aria-hidden="true" /> Load more
        </Button>
      ) : null}
    </nav>
  );
}

export function Breadcrumbs({ items }: { items: Array<{ label: string; href?: string }> }) {
  return (
    <nav className="hos-crumbs" aria-label="Breadcrumb">
      {items.map((item, i) => (
        <React.Fragment key={item.label}>
          {i > 0 ? <span aria-hidden="true">/</span> : null}
          {item.href && i < items.length - 1 ? (
            <a href={item.href}>{item.label}</a>
          ) : (
            <span aria-current={i === items.length - 1 ? "page" : undefined}>{item.label}</span>
          )}
        </React.Fragment>
      ))}
    </nav>
  );
}
