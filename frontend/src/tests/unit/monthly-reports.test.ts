import { describe, expect, it } from 'vitest';
import reportsData from '../../generated/monthly-reports.json';
import { META_DESCRIPTION_MAX_LENGTH, SITE_NAME } from '../../lib/seo';
import { LAST_WARD } from '../../lib/wards';
import {
  buildReportDescription,
  buildReportHeading,
  buildReportPath,
  buildReportTitle,
  describeSendingWards,
  findAdjacentReports,
  isReportMonth,
  topicLabel,
  topicReachFraction,
  type MonthlyReport,
  type MonthlyReportsFile,
} from '../../lib/monthly-reports';

function makeReport(month: string, overrides: Partial<MonthlyReport> = {}): MonthlyReport {
  return {
    month,
    newsletters: 259,
    sending_wards: ['1', '2', '3'],
    readable_wards: 2,
    topics: [
      { id: 'transportation', wards: 2, newsletters: 10, examples: [] },
      { id: 'parks_libraries', wards: 1, newsletters: 4, examples: [] },
    ],
    ...overrides,
  };
}

const LABELS = {
  transportation: 'Transportation',
  parks_libraries: 'Parks, libraries & recreation',
};

describe('report paths and headings', () => {
  it('builds paths, titles, and headings from the month', () => {
    expect(buildReportPath('2026-09')).toBe('/reports/2026-09');
    expect(buildReportHeading('2026-09')).toBe('What Chicago aldermen wrote about in September 2026');
    expect(buildReportTitle('2026-09')).toBe(
      `What Chicago Aldermen Wrote About in September 2026 - ${SITE_NAME}`,
    );
  });

  it('accepts only YYYY-MM months', () => {
    expect(isReportMonth('2026-09')).toBe(true);
    expect(isReportMonth('2026-13')).toBe(false);
    expect(isReportMonth('2026-9')).toBe(false);
  });
});

describe('buildReportDescription', () => {
  it('names the volume and the most widely mentioned topics within the meta length', () => {
    const description = buildReportDescription(makeReport('2026-09'), LABELS);
    expect(description).toBe(
      "September 2026 in Chicago aldermen's newsletters: 259 newsletters from 3 wards. Most widely mentioned: transportation; parks, libraries & recreation.",
    );
    expect(description.length).toBeLessThanOrEqual(META_DESCRIPTION_MAX_LENGTH);
  });
});

describe('findAdjacentReports', () => {
  const reports = [makeReport('2026-09'), makeReport('2026-08'), makeReport('2026-07')];

  it('finds the newer and older neighbors', () => {
    const { newer, older } = findAdjacentReports(reports, '2026-08');
    expect(newer?.month).toBe('2026-09');
    expect(older?.month).toBe('2026-07');
  });

  it('has no neighbor past either end or for unknown months', () => {
    expect(findAdjacentReports(reports, '2026-09').newer).toBeNull();
    expect(findAdjacentReports(reports, '2026-07').older).toBeNull();
    expect(findAdjacentReports(reports, '2025-01')).toEqual({ newer: null, older: null });
  });
});

describe('report figures', () => {
  it('describes ward counts with their denominators', () => {
    const report = makeReport('2026-09');
    expect(describeSendingWards(report)).toBe('3 of 50 wards');
    expect(topicReachFraction(report.topics[1], report)).toBe(0.5);
    expect(topicReachFraction(report.topics[1], { ...report, readable_wards: 0 })).toBe(0);
    expect(topicLabel(LABELS, 'unknown')).toBe('unknown');
  });
});

describe('committed monthly-reports.json', () => {
  const file = reportsData as MonthlyReportsFile;

  it('lists valid, unique months newest first', () => {
    const months = file.reports.map((report) => report.month);
    expect(months.every(isReportMonth)).toBe(true);
    expect(new Set(months).size).toBe(months.length);
    expect([...months].sort().reverse()).toEqual(months);
  });

  it('counts wards within their denominators and labels every topic', () => {
    for (const report of file.reports) {
      expect(new Set(report.sending_wards).size).toBe(report.sending_wards.length);
      expect(report.sending_wards.length).toBeLessThanOrEqual(LAST_WARD);
      expect(report.readable_wards).toBeLessThanOrEqual(report.sending_wards.length);
      for (const topic of report.topics) {
        expect(file.topics[topic.id]).toBeTruthy();
        expect(topic.wards).toBeLessThanOrEqual(report.readable_wards);
      }
    }
  });

  it('draws topic examples from that month and from different sending wards', () => {
    for (const report of file.reports) {
      for (const topic of report.topics) {
        const ids = topic.examples.map((example) => example.id);
        const wards = topic.examples.map((example) => example.ward);
        expect(new Set(ids).size).toBe(ids.length);
        expect(new Set(wards).size).toBe(wards.length);
        for (const example of topic.examples) {
          expect(example.date.startsWith(report.month)).toBe(true);
          expect(report.sending_wards).toContain(example.ward);
        }
      }
    }
  });

  it('publishes no rising terms or absent-ward lists', () => {
    for (const report of file.reports) {
      expect(report).not.toHaveProperty('rising');
      expect(report).not.toHaveProperty('absent_wards');
    }
  });
});
