/** The header lines of a Cloudflare Pages `_headers` rule for exactly this path pattern. */
export function headersForPattern(headersFile: string, pattern: string): string[] {
  const lines = headersFile.split(/\r?\n/);
  const start = lines.indexOf(pattern);
  if (start === -1) return [];
  const rule: string[] = [];
  for (const line of lines.slice(start + 1)) {
    if (!/^\s+\S/.test(line)) break;
    rule.push(line.trim());
  }
  return rule;
}
