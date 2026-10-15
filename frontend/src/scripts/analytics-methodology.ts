// Fills the data-driven parts of /analytics/methodology from the dashboard's JSON.
import {
  describeDataAsOf,
  findBroadCoverageWindow,
  listSourceWards,
  summarizeWardCoverage,
  type AnalyticsMetadata,
  type LensSummary,
  type NewsletterFact,
  type SourceCoverage,
} from "../lib/analytics";
import {
  describeBoilerplateRule,
  describeDefaultWindow,
  describeTopicDefinition,
  describeTopicMatching,
  pluralize,
} from "../lib/analytics-methodology";
import { renderTable } from "../lib/analytics-table";

export interface MethodologyData {
  metadata: AnalyticsMetadata;
  sources: { sources: SourceCoverage[] };
  lenses: LensSummary;
  newsletters: { newsletters: NewsletterFact[] };
}

function setText(id: string, text: string): HTMLElement | null {
  const element = document.getElementById(id);
  if (element) element.textContent = text;
  return element;
}

function renderCoverage(sources: SourceCoverage[]): void {
  const coverage = summarizeWardCoverage(sources, listSourceWards(sources));
  const absent = coverage.filter((ward) => ward.newsletters === 0).map((ward) => ward.ward);
  const archived = coverage.length - absent.length;
  setText("archive-summary", `${archived} of ${pluralize(coverage.length, "ward")} have newsletters here; city-wide figures cover only these.`);
  if (absent.length) {
    const absentWards = setText("absent-wards", `No newsletters in the archive: ${absent.join(", ")}.`);
    absentWards?.removeAttribute("hidden");
  }
  document.getElementById("coverage-table")?.replaceChildren(
    renderTable(
      [
        { label: "Ward", value: (row) => row.ward },
        { label: "Aldermen", value: (row) => row.aldermen.join(", ") },
        { label: "First newsletter", value: (row) => row.firstDate ?? "None" },
        { label: "Latest newsletter", value: (row) => row.lastDate ?? "" },
        { label: "Newsletters", value: (row) => row.newsletters, numeric: true },
      ],
      coverage,
    ),
  );
}

function renderTopics(summary: LensSummary): void {
  setText(
    "topic-rules",
    `${describeTopicMatching(summary)} Counts are of ${pluralize(summary.readable_newsletters, "newsletter")}.`,
  );
  const list = document.getElementById("topic-definitions");
  list?.replaceChildren(
    ...summary.lenses.flatMap((lens) => {
      const { title, body } = describeTopicDefinition(lens, summary.readable_newsletters);
      const term = document.createElement("dt");
      term.className = "font-semibold text-gray-900";
      term.textContent = title;
      const definition = document.createElement("dd");
      definition.textContent = body;
      return [term, definition];
    }),
  );
}

export function startMethodologyPage(data: MethodologyData): void {
  setText("methodology-data-as-of", describeDataAsOf(data.metadata));
  renderCoverage(data.sources.sources);
  renderTopics(data.lenses);
  setText("boilerplate-rule", describeBoilerplateRule(data.metadata));
  setText("default-window-rule", describeDefaultWindow(findBroadCoverageWindow(data.newsletters.newsletters)));
}
