/** Aggregate explicit profile outcomes; missing profiles are never passes. */
export function summarizeProfiles(expected, records) {
  const results = expected.map((name) => records.find((record) => record.profile === name));
  if (results.some((result) => !result || result.status === "failed")) return "failed";
  if (results.every((result) => result.status === "passed")) return "passed";
  if (results.every((result) => result.status === "skipped")) return "skipped";
  if (results.some((result) => result.status === "partial" || result.status === "skipped")) return "partial";
  return "failed";
}

/** Read Playwright test outcomes, including skipped tests, without treating skips as passes. */
export function playwrightReportStatus(report) {
  const tests = [];
  function walk(suite) {
    for (const spec of suite?.specs || []) for (const test of spec?.tests || []) tests.push(test);
    for (const child of suite?.suites || []) walk(child);
  }
  for (const suite of report?.suites || []) walk(suite);
  if (!tests.length) return "failed";
  const statuses = tests.map((test) => {
    const last = test.results?.at(-1)?.status;
    if (last) return last;
    if (test.outcome === "expected") return "passed";
    return test.outcome || "unknown";
  });
  if (statuses.some((status) => !["passed", "skipped"].includes(status))) return "failed";
  if (statuses.every((status) => status === "passed")) return "passed";
  if (statuses.every((status) => status === "skipped")) return "skipped";
  return "partial";
}
