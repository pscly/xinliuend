import { RRule, type Options as RRuleOptions } from "rrule";

import type { LocalDateTimeString } from "./types";

// 后端约定：tzid 固定为 Asia/Shanghai（UTC+8，无夏令时）。
// 因此这里把所有 LocalDateTimeString 视为“上海本地时间”，并显式在 UTC 毫秒之间互转，
// 以保证在不同运行环境下计算结果一致、可复现。
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
      `无效的 LocalDateTimeString：期望格式 YYYY-MM-DDTHH:mm:ss（长度=19），实际：${local}`,
    );
  }

  const yyyy = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  const hour = Number(m[4]);
  const minute = Number(m[5]);
  const second = Number(m[6]);

  // 将解析出的组件按“上海本地时间”解释，然后转换为 UTC 毫秒时间戳。
  const utcMs = Date.UTC(yyyy, month - 1, day, hour, minute, second) - SHANGHAI_OFFSET_MS;

  // 日历校验：通过 round-trip 来拒绝非法日期（例如 2026-02-31）。
  // 同时也保证格式化后的字符串仍保持 length=19 的契约。
  const roundTrip = formatUtcMsToShanghaiLocal(utcMs);
  if (roundTrip !== local) {
    throw new Error(`无效的 LocalDateTimeString（不存在的日期时间）：${local}`);
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
 * 将一个 RRULE 在“闭区间本地时间范围”内展开为 recurrence_id_local 列表。
 *
 * 错误处理策略：输入非法时抛出明确的 Error（而不是静默返回 []）。
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
    throw new Error(`无效的 RRULE 字符串：${msg}`);
  }

  const rule = new RRule({
    ...parsed,
    dtstart: new Date(dtstartUtcMs),
  } as RRuleOptions);

  const dates = rule.between(new Date(fromUtcMs), new Date(toUtcMs), true);
  return dates.map((d) => formatUtcMsToShanghaiLocal(d.getTime()));
}
