import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

const HTMLCOV_ROOT = path.resolve(process.cwd(), "..", "htmlcov");

const CONTENT_TYPES: Record<string, string> = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml; charset=utf-8",
};

function resolveHtmlcovPath(segments: string[]) {
  const relative = segments.length ? segments.join("/") : "index.html";
  const normalized = path.normalize(relative).replace(/^(\.\.(\/|\\|$))+/, "");
  return path.join(HTMLCOV_ROOT, normalized);
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ path?: string[] }> }
) {
  const resolvedParams = await params;
  const targetPath = resolveHtmlcovPath(resolvedParams?.path ?? []);

  try {
    const fileStat = await stat(targetPath);
    if (!fileStat.isFile()) {
      return NextResponse.json({ error: "Not found" }, { status: 404 });
    }

    let contents = await readFile(targetPath);
    const ext = path.extname(targetPath);
    const contentType = CONTENT_TYPES[ext] ?? "application/octet-stream";

    if (ext === ".html" && (resolvedParams?.path ?? []).length === 0) {
      const html = contents.toString("utf-8");
      const withBase = html.replace(
        "<head>",
        '<head>\n    <base href="/test/">'
      );
      contents = Buffer.from(withBase, "utf-8");
    }

    return new NextResponse(contents, {
      status: 200,
      headers: {
        "content-type": contentType,
      },
    });
  } catch {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }
}
