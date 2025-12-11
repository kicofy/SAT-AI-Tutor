export type MembershipOrder = {
  id: number;
  user_id?: number;
  plan: "monthly" | "quarterly";
  price_cents: number;
  currency: string;
  status: "pending" | "approved" | "rejected";
  user_note?: string | null;
  admin_note?: string | null;
  created_at: string;
  reviewed_at?: string | null;
  reviewed_by?: number | null;
  user?: {
    id: number;
    email?: string;
    username?: string | null;
  };
};

export type MembershipOrderPagination = {
  orders: MembershipOrder[];
  pagination: {
    page: number;
    per_page: number;
    pages: number;
    total: number;
    has_next: boolean;
    has_prev: boolean;
  };
};

