/**
 * Calendar-date helpers for interpreting user-entered dates as Chicago days.
 *
 * Newsletters are stored with a `timestamptz` received date. A user picking
 * "March 5" means March 5 in Chicago, so day boundaries are converted from
 * America/Chicago local midnight to UTC instants (DST-aware).
 */

export const CHICAGO_TIME_ZONE = "America/Chicago";

const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;
const MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000;

const chicagoWallClockFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: CHICAGO_TIME_ZONE,
  hourCycle: "h23",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const toUtcMidnight = (isoDate: string): number => {
  const [, year, month, day] = ISO_DATE_PATTERN.exec(isoDate) ?? [];
  return Date.UTC(Number(year), Number(month) - 1, Number(day));
};

/**
 * Returns `value` if it is a real calendar date in `YYYY-MM-DD` form
 * (the format produced by `<input type="date">`), otherwise null.
 * Rejects impossible dates such as 2026-02-30.
 */
export function parseIsoDate(value: string | null | undefined): string | null {
  const trimmed = value?.trim() ?? "";
  const match = ISO_DATE_PATTERN.exec(trimmed);
  if (!match) return null;

  const [, year, month, day] = match;
  const parsed = new Date(toUtcMidnight(trimmed));
  const isRealDate =
    parsed.getUTCFullYear() === Number(year) &&
    parsed.getUTCMonth() === Number(month) - 1 &&
    parsed.getUTCDate() === Number(day);

  return isRealDate ? trimmed : null;
}

/** Returns the `YYYY-MM-DD` date `days` after `isoDate`. */
export function addDaysToIsoDate(isoDate: string, days: number): string {
  return new Date(toUtcMidnight(isoDate) + days * MILLISECONDS_PER_DAY)
    .toISOString()
    .slice(0, 10);
}

/** Offset (ms) between Chicago wall-clock time and UTC at the given instant. */
const chicagoOffsetAt = (instant: number): number => {
  const parts = Object.fromEntries(
    chicagoWallClockFormatter
      .formatToParts(new Date(instant))
      .map(({ type, value }) => [type, Number(value)]),
  );
  const wallClockAsUtc = Date.UTC(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
    parts.second,
  );
  return wallClockAsUtc - instant;
};

/**
 * Returns the UTC ISO timestamp of midnight at the start of `isoDate` in
 * Chicago, e.g. "2026-01-15" -> "2026-01-15T06:00:00.000Z".
 */
export function startOfChicagoDayUtc(isoDate: string): string {
  const utcMidnight = toUtcMidnight(isoDate);
  const initialGuess = utcMidnight - chicagoOffsetAt(utcMidnight);
  // Re-check the offset at the guessed instant in case a DST change falls in between.
  return new Date(
    utcMidnight - chicagoOffsetAt(initialGuess),
  ).toISOString();
}
