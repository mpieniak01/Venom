/** Environment builds stay in a single named directory under the web workspace. */
export function nextDistDir(env = process.env) {
  const value = env.NEXT_DIST_DIR || ".next";
  if (!/^\.next(?:-[a-z0-9-]+)?$/.test(value)) {
    throw new Error("NEXT_DIST_DIR must be .next or .next-<environment>");
  }
  return value;
}
