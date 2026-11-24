"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  MoneyDisplay,
  PageHeader,
  Status,
  Table,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../shell";

type Location = { id: string; name: string };
type Item = {
  id: string;
  sku: string;
  name: string;
  category: string;
  unit: string;
  cost_price: string;
  reorder_level: string;
  is_active: boolean;
};
type Supplier = { id: string; name: string; phone: string | null; is_active: boolean };
type Balance = {
  item_id: string;
  location_id: string;
  sku: string;
  name: string;
  quantity_on_hand: string;
  reorder_level: string;
  is_low: boolean;
};
type Movement = {
  id: string;
  kind: string;
  quantity_delta: string;
  item_id: string;
  location_id: string;
  reason: string | null;
  occurred_at: string;
};
type PO = {
  id: string;
  status: string;
  supplier_id: string;
  location_id: string;
  lines: { id: string; item_id: string; quantity_ordered: string; quantity_received: string; unit_cost: string }[];
};
type Dashboard = {
  active_items: number;
  low_stock_count: number;
  out_of_stock_count: number;
  stock_valuation: string;
  recent_movements: Movement[];
  recent_purchase_orders: PO[];
};

export default function InventoryPage() {
  const router = useRouter();
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState("");
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [balances, setBalances] = useState<Balance[]>([]);
  const [movements, setMovements] = useState<Movement[]>([]);
  const [pos, setPos] = useState<PO[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sku, setSku] = useState("");
  const [itemName, setItemName] = useState("");
  const [supplierName, setSupplierName] = useState("");
  const [adjItem, setAdjItem] = useState("");
  const [adjQty, setAdjQty] = useState("");
  const [adjReason, setAdjReason] = useState("stock count");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/");
      return;
    }
    setLoading(true);
    const locParam = locationId ? `location_id=${locationId}` : "";
    const dashQs = locParam ? `?${locParam}` : "";
    const balQs = locParam ? `?${locParam}` : "";
    const listQs = locParam ? `&${locParam}` : "";
    Promise.all([
      api.get<Location[]>(`/api/v1/tenants/${t}/locations`, t),
      api.get<Dashboard>(`/api/v1/tenants/${t}/inventory/dashboard${dashQs}`, t),
      api.get<Item[]>(`/api/v1/tenants/${t}/inventory/items?active_only=true&q=${encodeURIComponent(q)}`, t),
      api.get<Supplier[]>(`/api/v1/tenants/${t}/inventory/suppliers?active_only=true`, t),
      api.get<Balance[]>(`/api/v1/tenants/${t}/inventory/balances${balQs}`, t),
      api.get<Movement[]>(`/api/v1/tenants/${t}/inventory/movements?limit=30${listQs}`, t),
      api.get<PO[]>(`/api/v1/tenants/${t}/inventory/purchase-orders?limit=30${listQs}`, t),
    ])
      .then(([locs, d, its, sups, bals, movs, orders]) => {
        setLocations(locs);
        setDash(d);
        setItems(its);
        setSuppliers(sups);
        setBalances(bals);
        setMovements(movs);
        setPos(orders);
        setError("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [locationId, q, router]);

  useEffect(() => {
    load();
  }, [load]);

  async function createItem(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    setBusy(true);
    try {
      await api.post(
        `/api/v1/tenants/${t}/inventory/items`,
        { sku, name: itemName, category: "general", unit: "each", cost_price: "0", reorder_level: "5" },
        t,
      );
      setSku("");
      setItemName("");
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function createSupplier(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    setBusy(true);
    try {
      await api.post(`/api/v1/tenants/${t}/inventory/suppliers`, { name: supplierName }, t);
      setSupplierName("");
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function adjust(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t || !locationId) {
      setError("Select a location before adjusting stock");
      return;
    }
    setBusy(true);
    try {
      await api.post(
        `/api/v1/tenants/${t}/inventory/adjustments`,
        {
          location_id: locationId,
          item_id: adjItem,
          quantity_delta: adjQty,
          reason: adjReason,
        },
        t,
      );
      setAdjQty("");
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function receiveFull(po: PO) {
    const t = getSelectedTenant();
    if (!t) return;
    setBusy(true);
    try {
      await api.post(
        `/api/v1/tenants/${t}/inventory/purchase-orders/${po.id}/receive`,
        {
          receipt_key: `recv-${po.id.slice(0, 8)}-${Date.now()}`,
          lines: po.lines.map((ln) => ({
            purchase_order_line_id: ln.id,
            quantity: String(
              Number(ln.quantity_ordered) - Number(ln.quantity_received),
            ),
            unit_cost: ln.unit_cost,
          })),
        },
        t,
      );
      load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell>
      <PageHeader
        title="Inventory"
        description="Clinic supplies and consumables. Stock is ledger-backed — balances are never edited directly."
      />
      {error ? (
        <Alert tone="danger" title="Inventory error">
          {error}
        </Alert>
      ) : null}
      <Field label="Location scope" htmlFor="inv-loc">
        {() => (
          <select
            id="inv-loc"
            className="hos-input"
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
          >
            <option value="">All authorized locations</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        )}
      </Field>
      {loading && !dash ? (
        <LoadingState label="Loading inventory" />
      ) : (
        <Tabs defaultValue="overview">
          <TabsList>
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="items">Items</TabsTrigger>
            <TabsTrigger value="stock">Stock</TabsTrigger>
            <TabsTrigger value="suppliers">Suppliers</TabsTrigger>
            <TabsTrigger value="orders">Purchase orders</TabsTrigger>
            <TabsTrigger value="movements">Movements</TabsTrigger>
          </TabsList>
          <TabsContent value="overview">
            <Card title="Dashboard">
              {dash ? (
                <>
                  <p>Active items: {dash.active_items}</p>
                  <p>Low stock: {dash.low_stock_count}</p>
                  <p>Out of stock: {dash.out_of_stock_count}</p>
                  <p>
                    Valuation: <MoneyDisplay amount={dash.stock_valuation} />
                  </p>
                </>
              ) : null}
            </Card>
          </TabsContent>
          <TabsContent value="items">
            <Card title="Catalog">
              <Field label="Search" htmlFor="inv-q">
                {() => (
                  <Input id="inv-q" value={q} onChange={(e) => setQ(e.target.value)} />
                )}
              </Field>
              {items.length === 0 ? (
                <EmptyState title="No items" />
              ) : (
                <Table
                  caption="Inventory items"
                  columns={
                    <>
                      <Th>SKU</Th>
                      <Th>Name</Th>
                      <Th>Unit</Th>
                      <Th>Cost</Th>
                      <Th>Reorder</Th>
                    </>
                  }
                >
                  {items.map((it) => (
                    <tr key={it.id}>
                      <Td>{it.sku}</Td>
                      <Td>{it.name}</Td>
                      <Td>{it.unit}</Td>
                      <Td>
                        <MoneyDisplay amount={it.cost_price} />
                      </Td>
                      <Td>{it.reorder_level}</Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
            <Card title="Add item">
              <form onSubmit={createItem}>
                <Field label="SKU" htmlFor="sku" required>
                  {() => <Input id="sku" value={sku} onChange={(e) => setSku(e.target.value)} required />}
                </Field>
                <Field label="Name" htmlFor="iname" required>
                  {() => (
                    <Input id="iname" value={itemName} onChange={(e) => setItemName(e.target.value)} required minLength={2} />
                  )}
                </Field>
                <Button type="submit" loading={busy}>
                  Create item
                </Button>
              </form>
            </Card>
          </TabsContent>
          <TabsContent value="stock">
            <Card title="Stock levels">
              {balances.length === 0 ? (
                <EmptyState title="No stock balances yet" />
              ) : (
                <Table
                  caption="On-hand stock"
                  columns={
                    <>
                      <Th>Item</Th>
                      <Th>Qty</Th>
                      <Th>Status</Th>
                    </>
                  }
                >
                  {balances.map((b) => (
                    <tr key={`${b.location_id}-${b.item_id}`}>
                      <Td>
                        {b.name} ({b.sku})
                      </Td>
                      <Td>{b.quantity_on_hand}</Td>
                      <Td>
                        <Status value={b.is_low ? "urgent" : "current"} />
                      </Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
            <Card title="Adjust stock">
              <form onSubmit={adjust}>
                <p className="hos-helper">Requires a selected location. Positive or negative delta.</p>
                <Field label="Item" htmlFor="adj-item" required>
                  {() => (
                    <select
                      id="adj-item"
                      className="hos-input"
                      value={adjItem}
                      onChange={(e) => setAdjItem(e.target.value)}
                      required
                    >
                      <option value="">Select</option>
                      {items.map((it) => (
                        <option key={it.id} value={it.id}>
                          {it.sku} — {it.name}
                        </option>
                      ))}
                    </select>
                  )}
                </Field>
                <Field label="Quantity delta" htmlFor="adj-qty" required>
                  {() => (
                    <Input id="adj-qty" value={adjQty} onChange={(e) => setAdjQty(e.target.value)} required />
                  )}
                </Field>
                <Field label="Reason" htmlFor="adj-reason" required>
                  {() => (
                    <Input id="adj-reason" value={adjReason} onChange={(e) => setAdjReason(e.target.value)} required />
                  )}
                </Field>
                <Button type="submit" loading={busy}>
                  Post adjustment
                </Button>
              </form>
            </Card>
          </TabsContent>
          <TabsContent value="suppliers">
            <Card title="Suppliers">
              {suppliers.length === 0 ? (
                <EmptyState title="No suppliers" />
              ) : (
                <Table
                  caption="Suppliers"
                  columns={
                    <>
                      <Th>Name</Th>
                      <Th>Phone</Th>
                    </>
                  }
                >
                  {suppliers.map((s) => (
                    <tr key={s.id}>
                      <Td>{s.name}</Td>
                      <Td>{s.phone ?? "—"}</Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
            <Card title="Add supplier">
              <form onSubmit={createSupplier}>
                <Field label="Name" htmlFor="sname" required>
                  {() => (
                    <Input id="sname" value={supplierName} onChange={(e) => setSupplierName(e.target.value)} required />
                  )}
                </Field>
                <Button type="submit" loading={busy}>
                  Create supplier
                </Button>
              </form>
            </Card>
          </TabsContent>
          <TabsContent value="orders">
            <Card title="Purchase orders">
              {pos.length === 0 ? (
                <EmptyState title="No purchase orders" />
              ) : (
                <Table
                  caption="Purchase orders"
                  columns={
                    <>
                      <Th>Order</Th>
                      <Th>Status</Th>
                      <Th>Lines</Th>
                      <Th>Actions</Th>
                    </>
                  }
                >
                  {pos.map((po) => (
                    <tr key={po.id}>
                      <Td>{po.id.slice(0, 8)}</Td>
                      <Td>
                        <Status value={po.status} />
                      </Td>
                      <Td>{po.lines.length}</Td>
                      <Td>
                        {po.status === "ordered" || po.status === "partially_received" ? (
                          <Button type="button" size="sm" loading={busy} onClick={() => receiveFull(po)}>
                            Receive remaining
                          </Button>
                        ) : null}
                      </Td>
                    </tr>
                  ))}
                </Table>
              )}
              <p className="hos-helper">
                Create draft orders via API or a future dedicated form; submit then receive here.
              </p>
            </Card>
          </TabsContent>
          <TabsContent value="movements">
            <Card title="Stock movements">
              {movements.length === 0 ? (
                <EmptyState title="No movements" />
              ) : (
                <Table
                  caption="Ledger"
                  columns={
                    <>
                      <Th>When</Th>
                      <Th>Kind</Th>
                      <Th>Delta</Th>
                      <Th>Reason</Th>
                    </>
                  }
                >
                  {movements.map((m) => (
                    <tr key={m.id}>
                      <Td>{new Date(m.occurred_at).toLocaleString()}</Td>
                      <Td>{m.kind}</Td>
                      <Td>{m.quantity_delta}</Td>
                      <Td>{m.reason ?? "—"}</Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
          </TabsContent>
        </Tabs>
      )}
    </Shell>
  );
}
