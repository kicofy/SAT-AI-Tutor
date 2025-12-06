import { UserProfile } from "@/types/auth";

export type Pagination = {
  page: number;
  per_page: number;
  pages: number;
  total: number;
  has_next: boolean;
  has_prev: boolean;
};

export type PaginatedResponse<T> = {
  items: T[];
  pagination: Pagination;
};

export type AdminUser = {
  id: number;
  email: string;
  username: string;
  role: "student" | "admin";
  is_email_verified: boolean;
  created_at?: string | null;
  profile?: UserProfile | null;
};

export type AdminUserDetail = {
  user: AdminUser;
};

export type AdminQuestion = {
  id: number;
  question_uid?: string | null;
  section: string;
  sub_section?: string | null;
  difficulty_level?: number | null;
  stem_text?: string | null;
  skill_tags?: string[];
  correct_answer?: { value?: string | null } | null;
  choices?: Record<string, string>;
  source?: {
    id: number;
    filename?: string | null;
    original_name?: string | null;
  } | null;
};

export type AdminSource = {
  id: number;
  filename: string;
  original_name?: string | null;
  total_pages?: number | null;
  created_at?: string | null;
  question_count?: number;
};

export type AdminSourceDetail = {
  source: AdminSource;
  questions: AdminQuestion[];
  pagination: Pagination;
};

