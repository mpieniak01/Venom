// These are the operator's common transitions. The rest of the menu waits for
// pointer or keyboard intent instead of prefetching every visible route.
const PRIORITY_ROUTES = new Set(["/", "/chat", "/voice", "/models"]);
export function isPriorityNavigation(href: string): boolean {
  return PRIORITY_ROUTES.has(href);
}
