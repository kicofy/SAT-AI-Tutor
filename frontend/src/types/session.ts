export type QuestionPassage = {
  id?: number;
  content_text: string;
  metadata?: Record<string, unknown>;
};

export type QuestionFigureRef = {
  id: number;
  url: string;
  description?: string | null;
  bbox?: Record<string, unknown> | null;
};

export type QuestionAnswer = {
  value?: string;
  [key: string]: unknown;
};

export type SessionQuestion = {
  question_id: number;
  stem_text: string;
  choices: Record<string, string>;
  section: string;
  sub_section?: string | null;
  passage?: QuestionPassage | null;
  has_figure?: boolean;
  figures?: QuestionFigureRef[];
  correct_answer?: QuestionAnswer;
};

export type SessionProgressEntry = {
  question_id: number;
  log_id?: number;
  answered_at?: string;
  is_correct?: boolean;
  user_answer?: QuestionAnswer | null;
};

export type Session = {
  id: number;
  questions_assigned: SessionQuestion[];
  questions_done?: SessionProgressEntry[];
  started_at?: string;
  ended_at?: string | null;
};

export type StartSessionPayload = {
  num_questions: number;
  section?: string;
};

export type AnswerPayload = {
  session_id: number;
  question_id: number;
  user_answer: { value: string };
  time_spent_sec?: number;
};

export type AnswerResponse = {
  is_correct: boolean;
  log_id: number;
};

export type ExplanationResponse = {
  explanation: Record<string, unknown>;
};

