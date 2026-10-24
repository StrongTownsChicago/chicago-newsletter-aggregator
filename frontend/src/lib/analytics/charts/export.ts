// PNG export for dashboard charts with title, window, caption, data date, site
// and caveat. SVGs, legend swatches and marked text are drawn onto a canvas at
// their on-page positions.

export const EXPORT_CAVEAT = "Newsletters in the archive only; not every ward is covered.";

/** Marks an HTML element whose text is drawn into the export (SVGs are always drawn). */
export const EXPORT_TEXT_ATTRIBUTE = "data-export-text";
/** Marks an HTML legend swatch drawn into the export as a filled square or dot. */
export const EXPORT_SWATCH_ATTRIBUTE = "data-export-swatch";

const EXPORT_PADDING = 24;
const EXPORT_MIN_WIDTH = 640;
/** Pixel density of the exported image, so it stays sharp on high-resolution screens. */
const EXPORT_SCALE = 2;
/** Canvas limits that hold on every major browser (iOS Safari is the tightest). */
const MAX_CANVAS_PIXELS = 16_777_216;
const MAX_CANVAS_SIDE = 16_384;
const SECTION_GAP = 12;
const FONT_FAMILY = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const EXPORT_COLORS = { background: "#ffffff", ink: "#111827", mutedInk: "#4b5563" };
const MAX_FILE_NAME_SLUG_LENGTH = 60;
/** The download's object URL is released after this delay, once the browser has started saving it. */
const DOWNLOAD_URL_RELEASE_DELAY_MS = 1000;

export interface ExportTextLine {
  text: string;
  role: "title" | "body" | "note";
}

const LINE_STYLES: Record<ExportTextLine["role"], { font: string; color: string; lineHeight: number }> = {
  title: { font: `600 20px ${FONT_FAMILY}`, color: EXPORT_COLORS.ink, lineHeight: 28 },
  body: { font: `14px ${FONT_FAMILY}`, color: EXPORT_COLORS.ink, lineHeight: 20 },
  note: { font: `12px ${FONT_FAMILY}`, color: EXPORT_COLORS.mutedInk, lineHeight: 17 },
};

export interface ChartExportContext {
  title: string;
  /** The window and wards shown, e.g. "Feb 2026 – Oct 2026 · All wards". */
  scope: string;
  /** The denominator caption under the chart title on the page. */
  caption: string;
  /** A sentence, e.g. "Data as of Oct 14, 2026, 9:00 PM from 2,215 newsletters." */
  dataAsOf: string;
  siteName: string;
  /** The page link that reproduces this view. */
  pageUrl: string;
}

/** Lines above the chart: title, scope and the denominator caption. */
export function buildExportHeader(context: ChartExportContext): ExportTextLine[] {
  return [
    { text: context.title, role: "title" as const },
    { text: context.scope, role: "body" as const },
    { text: context.caption, role: "note" as const },
  ].filter((line) => line.text.trim() !== "");
}

/** Lines below the chart: data date, caveat and where it came from. */
export function buildExportFooter(context: ChartExportContext): ExportTextLine[] {
  return [
    { text: `${context.dataAsOf} ${EXPORT_CAVEAT}`, role: "note" },
    { text: `${context.siteName} · ${context.pageUrl}`, role: "note" },
  ];
}

/**
 * Break text into lines no wider than maxWidth, by words. A single word wider
 * than the line (such as a long URL) is broken by characters.
 */
export function wrapText(text: string, maxWidth: number, measure: (text: string) => number): string[] {
  const lines: string[] = [];
  let line = "";
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const candidate = line ? `${line} ${word}` : word;
    if (measure(candidate) <= maxWidth) {
      line = candidate;
      continue;
    }
    if (line) lines.push(line);
    line = "";
    let rest = word;
    while (measure(rest) > maxWidth && rest.length > 1) {
      let cut = rest.length - 1;
      while (cut > 1 && measure(rest.slice(0, cut)) > maxWidth) cut -= 1;
      lines.push(rest.slice(0, cut));
      rest = rest.slice(cut);
    }
    line = rest;
  }
  if (line) lines.push(line);
  return lines;
}

/**
 * The export's pixel density: EXPORT_SCALE, lowered for very large charts so
 * the canvas stays within browser limits instead of failing to encode.
 */
export function chooseExportScale(width: number, height: number): number {
  return Math.min(
    EXPORT_SCALE,
    Math.sqrt(MAX_CANVAS_PIXELS / (width * height)),
    MAX_CANVAS_SIDE / width,
    MAX_CANVAS_SIDE / height,
  );
}

/** "civic-calendar-2026-10-14.png": a readable file name from the chart title. */
export function buildExportFileName(title: string, date: Date): string {
  const slug =
    title
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, MAX_FILE_NAME_SLUG_LENGTH)
      .replace(/-+$/, "") || "chart";
  return `${slug}-${date.toISOString().slice(0, 10)}.png`;
}

// ---------------------------------------------------------------------------
// Browser-only rendering

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

type ExportItem =
  | { kind: "svg"; element: SVGSVGElement; box: Box }
  | { kind: "swatch"; color: string; outline: string; round: boolean; box: Box }
  | { kind: "text"; text: string; font: string; color: string; lineHeight: number; box: Box };

/** Line height when the computed style says "normal", as a multiple of the font size. */
const NORMAL_LINE_HEIGHT = 1.2;

/** The canvas font for an element; the computed `font` shorthand is empty in some browsers. */
function canvasFontOf(style: CSSStyleDeclaration): string {
  return `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
}

/** Rounded fully enough to read as a dot (Tailwind's rounded-full computes to a huge radius). */
function isRound(style: CSSStyleDeclaration, box: Box): boolean {
  return Number.parseFloat(style.borderRadius) >= Math.min(box.width, box.height) / 2;
}

function lineHeightOf(style: CSSStyleDeclaration): number {
  const lineHeight = Number.parseFloat(style.lineHeight);
  return Number.isNaN(lineHeight) ? Number.parseFloat(style.fontSize) * NORMAL_LINE_HEIGHT : lineHeight;
}

/**
 * Position of an element inside the container's full content: its on-screen
 * offset plus however far it and the container are scrolled, so a chart that
 * is scrolled sideways on a narrow screen is still exported whole.
 */
function boxWithin(element: Element, container: HTMLElement): Box {
  const rect = element.getBoundingClientRect();
  const origin = container.getBoundingClientRect();
  let scrollX = 0;
  let scrollY = 0;
  for (let ancestor = element.parentElement; ancestor; ancestor = ancestor.parentElement) {
    scrollX += ancestor.scrollLeft;
    scrollY += ancestor.scrollTop;
    if (ancestor === container) break;
  }
  return {
    x: rect.left - origin.left + scrollX,
    y: rect.top - origin.top + scrollY,
    width: rect.width,
    height: rect.height,
  };
}

/** How to draw one visible element: as an SVG, a legend swatch or a line of text. */
function exportItemFor(element: Element, box: Box): ExportItem {
  if (element instanceof SVGSVGElement) return { kind: "svg", element, box };
  const style = getComputedStyle(element);
  if (element.hasAttribute(EXPORT_SWATCH_ATTRIBUTE)) {
    return {
      kind: "swatch",
      color: style.backgroundColor,
      outline: element.getAttribute(EXPORT_SWATCH_ATTRIBUTE) ?? "",
      round: isRound(style, box),
      box,
    };
  }
  return {
    kind: "text",
    text: element.textContent?.trim() ?? "",
    font: canvasFontOf(style),
    color: style.color,
    lineHeight: lineHeightOf(style),
    box,
  };
}

/** Elements to draw, in document order: top-level SVGs, legend swatches and marked text. */
function collectExportItems(container: HTMLElement): ExportItem[] {
  const selector = `svg, [${EXPORT_SWATCH_ATTRIBUTE}], [${EXPORT_TEXT_ATTRIBUTE}]`;
  const items: ExportItem[] = [];
  for (const element of container.querySelectorAll(selector)) {
    if (element.parentElement?.closest("svg")) continue;
    const box = boxWithin(element, container);
    if (box.width === 0 || box.height === 0) continue;
    items.push(exportItemFor(element, box));
  }
  return items;
}

function loadSvgImage(svg: SVGSVGElement, box: Box): Promise<HTMLImageElement> {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(box.width));
  clone.setAttribute("height", String(box.height));
  const markup = new XMLSerializer().serializeToString(clone);
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("Could not draw the chart image."));
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`;
  });
}

function layoutLines(
  context: CanvasRenderingContext2D,
  lines: ExportTextLine[],
  maxWidth: number,
): { line: ExportTextLine; text: string }[] {
  return lines.flatMap((line) => {
    context.font = LINE_STYLES[line.role].font;
    return wrapText(line.text, maxWidth, (text) => context.measureText(text).width).map((text) => ({ line, text }));
  });
}

function linesHeight(lines: { line: ExportTextLine }[]): number {
  return lines.reduce((total, { line }) => total + LINE_STYLES[line.role].lineHeight, 0);
}

function drawLines(context: CanvasRenderingContext2D, lines: { line: ExportTextLine; text: string }[], top: number): void {
  let y = top;
  context.textBaseline = "top";
  for (const { line, text } of lines) {
    const style = LINE_STYLES[line.role];
    context.font = style.font;
    context.fillStyle = style.color;
    context.fillText(text, EXPORT_PADDING, y);
    y += style.lineHeight;
  }
}

/** Draw the container's chart with its header and footer onto a new canvas. */
export async function renderChartCanvas(container: HTMLElement, exportContext: ChartExportContext): Promise<HTMLCanvasElement> {
  const items = collectExportItems(container);
  const contentWidth = Math.max(...items.map((item) => item.box.x + item.box.width), 0);
  const contentHeight = Math.max(...items.map((item) => item.box.y + item.box.height), 0);
  const width = Math.max(EXPORT_MIN_WIDTH, Math.ceil(contentWidth) + EXPORT_PADDING * 2);
  const textWidth = width - EXPORT_PADDING * 2;

  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) throw new Error("This browser cannot draw images.");
  const header = layoutLines(context, buildExportHeader(exportContext), textWidth);
  const footer = layoutLines(context, buildExportFooter(exportContext), textWidth);
  const chartTop = EXPORT_PADDING + linesHeight(header) + SECTION_GAP;
  const footerTop = chartTop + Math.ceil(contentHeight) + SECTION_GAP;
  const height = footerTop + linesHeight(footer) + EXPORT_PADDING;

  const scale = chooseExportScale(width, height);
  canvas.width = Math.floor(width * scale);
  canvas.height = Math.floor(height * scale);
  context.scale(scale, scale);
  context.fillStyle = EXPORT_COLORS.background;
  context.fillRect(0, 0, width, height);
  drawLines(context, header, EXPORT_PADDING);

  const images = await Promise.all(
    items.map((item) => (item.kind === "svg" ? loadSvgImage(item.element, item.box) : Promise.resolve(null))),
  );
  items.forEach((item, position) => {
    const x = EXPORT_PADDING + item.box.x;
    const y = chartTop + item.box.y;
    if (item.kind === "svg") {
      context.drawImage(images[position] as HTMLImageElement, x, y, item.box.width, item.box.height);
    } else if (item.kind === "swatch") {
      context.beginPath();
      if (item.round) {
        context.arc(x + item.box.width / 2, y + item.box.height / 2, item.box.width / 2, 0, Math.PI * 2);
      } else {
        context.rect(x, y, item.box.width, item.box.height);
      }
      context.fillStyle = item.color;
      context.fill();
      if (item.outline) {
        context.strokeStyle = item.outline;
        context.stroke();
      }
    } else {
      // Re-wrap to the element's width, which matches how the page wrapped it.
      context.font = item.font;
      context.fillStyle = item.color;
      context.textBaseline = "middle";
      const lines = wrapText(item.text, item.box.width + 1, (text) => context.measureText(text).width);
      lines.forEach((line, index) => context.fillText(line, x, y + item.lineHeight * (index + 0.5)));
    }
  });
  drawLines(context, footer, footerTop);
  return canvas;
}

/** Render the chart in `container` and download it as a PNG. */
export async function downloadChartPng(container: HTMLElement, exportContext: ChartExportContext): Promise<void> {
  const canvas = await renderChartCanvas(container, exportContext);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) throw new Error("Could not create the image.");
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = buildExportFileName(exportContext.title, new Date());
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), DOWNLOAD_URL_RELEASE_DELAY_MS);
}
