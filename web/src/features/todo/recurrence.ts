import { RRule, type Options as RRuleOptions } from "rrule";

import type { LocalDateTimeString } from "./types";

// Backend contract: tzid is fixed to Asia/Shanghai (UTC+8, no DST).
// We treat all LocalDateTimeString values as "Asia/Shanghai local" and explicitly
// convert to/from UTC milliseconds so results are deterministic across environments.
const SHANGHAI_OFFSET_MS = 8 * 60 * 60 * 1000;

const LOCAL_DATE_TIME_RE =
  /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/;

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

function formatUtcMsToShanghaiLocal(utcMs: number): LocalDateTimeString {
  const localMs = utcMs + SHANGHAI_OFFSET_MS;
  const d = new Date(localMs);
  const yyyy = d.getUTCFullYear();
  const mm = pad2(d.getUTCMonth() + 1);
  const dd = pad2(d.getUTCDate());
  const hh = pad2(d.getUTCHours());
  const mi = pad2(d.getUTCMinutes());
  const ss = pad2(d.getUTCSeconds());
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}`;
}

function parseShanghaiLocalToUtcMs(local: LocalDateTimeString): number {
  const m = LOCAL_DATE_TIME_RE.exec(local);
  if (!m) {
    throw new Error(
      `Invalid LocalDateTimeString: expected YYYY-MM-DDTHH:mm:ss (len=19), got: ${local}`,
    );
  }

  const yyyy = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  const hour = Number(m[4]);
  const minute = Number(m[5]);
  const second = Number(m[6]);

  // Interpret the components as Asia/Shanghai local time, then convert to UTC.
  const utcMs = Date.UTC(yyyy, month - 1, day, hour, minute, second) - SHANGHAI_OFFSET_MS;

  // Calendar validation (e.g. reject 2026-02-31) by round-tripping.
  // This also guarantees the formatted string keeps length=19.
  const roundTrip = formatUtcMsToShanghaiLocal(utcMs);
  if (roundTrip !== local) {
    throw new Error(`Invalid LocalDateTimeString (non-existent datetime): ${local}`);
  }

  return utcMs;
}

export type ExpandRruleSeed = {
  rrule: string;
  dtstart_local: LocalDateTimeString;
};

export type ExpandLocalRange = {
  from: LocalDateTimeString;
  to: LocalDateTimeString;
};

/**
 * Expands an RRULE into local recurrence_id strings within an inclusive local range.
 *
 * Error handling choice: invalid inputs throw a clear Error (rather than returning []).
 */
export function expandRruleToLocalIds(
  { rrule, dtstart_local }: ExpandRruleSeed,
  { from, to }: ExpandLocalRange,
): LocalDateTimeString[] {
  const fromUtcMs = parseShanghaiLocalToUtcMs(from);
  const toUtcMs = parseShanghaiLocalToUtcMs(to);
  if (fromUtcMs > toUtcMs) return [];

  const dtstartUtcMs = parseShanghaiLocalToUtcMs(dtstart_local);

  let parsed: Partial<RRuleOptions>;
  try {
    parsed = RRule.parseString(rrule);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Invalid RRULE string: ${msg}`);
  }

  const rule = new RRule({
    ...parsed,
    dtstart: new Date(dtstartUtcMs),
  } as RRuleOptions);

  const dates = rule.between(new Date(fromUtcMs), new Date(toUtcMs), true);
  return dates.map((d) => formatUtcMsToShanghaiLocal(d.getTime()));
}
