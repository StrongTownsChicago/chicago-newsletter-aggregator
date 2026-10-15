// Helpers for the prerendered /reports pages. Data: src/data/monthly-reports.json,
// from backend/analytics/monthly_reports.py.

import { formatLongMonth } from "./archive-months";
import { SITE_NAME, truncateDescription } from "./seo";
import { REPORTS_INDEX_PATH } from "./site";
import { LAST_WARD } from "./wards";

export interface ReportExample {
  id: string;
  subject: string;
  ward: string | null;
  date: string;
}

export interface ReportTopic {
  id: string;
  /** Wards with at least one readable newsletter that month mentioning the topic. */
  wards: number;
  newsletters: number;
  examples: ReportExample[];
}

export interface MonthlyReport {
  month: string;
  newsletters: number;
  sending_wards: string[];
  /** Wards with a readable newsletter that month: the topic reach denominator. */
  readable_wards: number;
  topics: ReportTopic[];
}

export interface MonthlyReportsFile {
  data_through: string | null;
  topics: Record<string, string>;
  /** Newest first. */
  reports: MonthlyReport[];
}

/** Topics named in a report's description. */
const DESCRIPTION_TOPIC_COUNT = 3;
/** Topics previewed per report on the index page. */
export const INDEX_TOPIC_PREVIEW_COUNT = 3;

const MONTH_KEY_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;

export function isReportMonth(month: string): boolean {
  return MONTH_KEY_PATTERN.test(month);
}

export function buildReportPath(month: string): string {
  return `${REPORTS_INDEX_PATH}/${month}`;
}

export function buildReportHeading(month: string): string {
  return `What Chicago aldermen wrote about in ${formatLongMonth(month)}`;
}

export function buildReportTitle(month: string): string {
  return `What Chicago Aldermen Wrote About in ${formatLongMonth(month)} - ${SITE_NAME}`;
}

export function topicLabel(labels: Record<string, string>, topicId: string): string {
  return labels[topicId] ?? topicId;
}

/** Meta description naming the topics the most wards mentioned. */
export function buildReportDescription(
  report: MonthlyReport,
  labels: Record<string, string>,
): string {
  const leading = report.topics
    .slice(0, DESCRIPTION_TOPIC_COUNT)
    .map((topic) => topicLabel(labels, topic.id).toLowerCase())
    .join("; ");
  const topics = leading ? ` Most widely mentioned: ${leading}.` : "";
  return truncateDescription(
    `${formatLongMonth(report.month)} in Chicago aldermen's newsletters: ${report.newsletters} newsletters from ${report.sending_wards.length} wards.${topics}`,
  );
}

export const REPORTS_INDEX_TITLE = `Monthly Reports on Chicago Alderman Newsletters - ${SITE_NAME}`;
export const REPORTS_INDEX_DESCRIPTION =
  "Month-by-month summaries of Chicago aldermen's newsletters: topics by how many wards mentioned them, with example newsletters.";

export interface AdjacentReports {
  newer: MonthlyReport | null;
  older: MonthlyReport | null;
}

/** The reports just before and after a month, for previous/next links. */
export function findAdjacentReports(reports: MonthlyReport[], month: string): AdjacentReports {
  const newestFirst = [...reports].sort((a, b) => b.month.localeCompare(a.month));
  const index = newestFirst.findIndex((report) => report.month === month);
  if (index === -1) {
    return { newer: null, older: null };
  }
  return {
    newer: newestFirst[index - 1] ?? null,
    older: newestFirst[index + 1] ?? null,
  };
}

/** "38 of 50 wards" */
export function describeSendingWards(report: MonthlyReport): string {
  return `${report.sending_wards.length} of ${LAST_WARD} wards`;
}

/** Topic reach as a fraction of the wards whose newsletters could be read. */
export function topicReachFraction(topic: ReportTopic, report: MonthlyReport): number {
  return report.readable_wards > 0 ? topic.wards / report.readable_wards : 0;
}
