import type { WhereResult } from "../api";

export interface WhereDraft { before: string; contexts: string; allCategories: boolean }
export interface WhereQuery { before?: string; contexts: number; all_categories: boolean }
export interface WhereState {
  day: string; draft: WhereDraft; applied: WhereQuery; request: number | null;
  busy: boolean; error: string | null; result: { data: WhereResult; query: WhereQuery } | null;
}
export function initialWhere(day: string, isToday: boolean): WhereState {
  return { day, draft: { before: "", contexts: "3", allCategories: false },
    applied: { before: isToday ? undefined : day, contexts: 3, all_categories: false },
    request: null, busy: false, error: null, result: null };
}
export function whereQuery(draft: WhereDraft, day: string, isToday: boolean): WhereQuery {
  return { before: draft.before ? new Date(draft.before).toISOString() : isToday ? undefined : day,
    contexts: Number(draft.contexts), all_categories: draft.allCategories };
}
type Action =
  | { type: "reset"; day: string; isToday: boolean }
  | { type: "edit"; draft: WhereDraft }
  | { type: "start"; day: string; ticket: number }
  | { type: "resolve"; ticket: number; data: WhereResult; query: WhereQuery }
  | { type: "reject"; ticket: number; error: string }
  | { type: "input-error"; error: string };
export function whereReducer(state: WhereState, action: Action): WhereState {
  if (action.type === "reset") return initialWhere(action.day, action.isToday);
  if (action.type === "edit") return { ...state, draft: action.draft, result: null, request: null, busy: false, error: null };
  if (action.type === "input-error") return { ...state, error: action.error };
  if (action.type === "start") return action.day === state.day ? { ...state, request: action.ticket, busy: true, result: null, error: null } : state;
  if (action.ticket !== state.request) return state;
  if (action.type === "reject") return { ...state, request: null, busy: false, error: action.error };
  return { ...state, request: null, busy: false, error: null, applied: action.query, result: { data: action.data, query: action.query } };
}
