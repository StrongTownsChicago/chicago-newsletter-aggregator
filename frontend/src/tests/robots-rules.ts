/** A robots.txt line's lowercased field and its value, or null for a comment or blank line. */
function parseRobotsLine(rawLine: string): { field: string; value: string } | null {
  const line = rawLine.replace(/#.*/, "").trim();
  const separator = line.indexOf(":");
  if (separator === -1) return null;
  return { field: line.slice(0, separator).trim().toLowerCase(), value: line.slice(separator + 1).trim() };
}

interface RobotsGroup {
  agents: string[];
  disallow: string[];
}

/** robots.txt's groups: each run of consecutive User-agent lines with the rules after it. */
function parseRobotsGroups(robotsTxt: string): RobotsGroup[] {
  const groups: RobotsGroup[] = [];
  let lastLineWasAgent = false;
  for (const parsed of robotsTxt.split(/\r?\n/).map(parseRobotsLine)) {
    if (!parsed) continue;
    const { field, value } = parsed;
    if (field === "user-agent") {
      if (!lastLineWasAgent) groups.push({ agents: [], disallow: [] });
      groups[groups.length - 1].agents.push(value.toLowerCase());
      lastLineWasAgent = true;
      continue;
    }
    lastLineWasAgent = false;
    if (field === "disallow" && value !== "" && groups.length > 0) {
      groups[groups.length - 1].disallow.push(value);
    }
  }
  return groups;
}

/**
 * The Disallow rules robots.txt applies to one user agent: those of the group
 * naming it (case-insensitively), else those of the `*` group. A group is a run
 * of consecutive User-agent lines followed by its rules.
 */
export function disallowRulesFor(robotsTxt: string, userAgent: string): string[] {
  const groups = parseRobotsGroups(robotsTxt);
  const matchingGroup =
    groups.find(({ agents }) => agents.includes(userAgent.toLowerCase())) ??
    groups.find(({ agents }) => agents.includes("*"));
  return matchingGroup?.disallow ?? [];
}

export function isPathDisallowed(disallowRules: string[], path: string): boolean {
  return disallowRules.some((rule) => path.startsWith(rule));
}
