/**
 * The Disallow rules robots.txt applies to one user agent: those of the group
 * naming it (case-insensitively), else those of the `*` group. A group is a run
 * of consecutive User-agent lines followed by its rules.
 */
export function disallowRulesFor(robotsTxt: string, userAgent: string): string[] {
  const groups: { agents: string[]; disallow: string[] }[] = [];
  let lastLineWasAgent = false;
  for (const rawLine of robotsTxt.split(/\r?\n/)) {
    const line = rawLine.replace(/#.*/, "").trim();
    const separator = line.indexOf(":");
    if (separator === -1) continue;
    const field = line.slice(0, separator).trim().toLowerCase();
    const value = line.slice(separator + 1).trim();
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
  const matchingGroup =
    groups.find(({ agents }) => agents.includes(userAgent.toLowerCase())) ??
    groups.find(({ agents }) => agents.includes("*"));
  return matchingGroup?.disallow ?? [];
}

export function isPathDisallowed(disallowRules: string[], path: string): boolean {
  return disallowRules.some((rule) => path.startsWith(rule));
}
