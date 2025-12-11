import { api } from "@/lib/http";
import type { MembershipOrder, MembershipOrderPagination } from "@/types/membership";

export async function createMembershipOrder(plan: "monthly" | "quarterly", note?: string) {
  const { data } = await api.post<{ order: MembershipOrder }>("/api/membership/orders", {
    plan,
    note: note?.trim() || undefined,
  });
  return data.order;
}

export async function listMembershipOrders(): Promise<MembershipOrder[]> {
  const { data } = await api.get<{ orders: MembershipOrder[] }>("/api/membership/orders");
  return data.orders;
}

export async function listMembershipOrdersAdmin(params: {
  page?: number;
  per_page?: number;
  status?: string;
} = {}): Promise<MembershipOrderPagination> {
  const { data } = await api.get<MembershipOrderPagination>("/api/admin/membership/orders", {
    params,
  });
  return data;
}

export async function decideMembershipOrder(
  orderId: number,
  payload: { action: "approve" | "reject"; note?: string }
) {
  const { data } = await api.post(`/api/admin/membership/orders/${orderId}/decision`, payload);
  return data as { order: MembershipOrder; membership?: unknown };
}

