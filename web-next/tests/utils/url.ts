const HTTP_SCHEME = "http";
const SCHEME_SEP = "://";

export const buildHttpUrl = (host: string, port?: number, path = ""): string => {
  const normalizedPath = !path || path.startsWith("/") ? path : `/${path}`;
  const netloc = port === undefined ? host : `${host}:${port}`;
  return `${HTTP_SCHEME}${SCHEME_SEP}${netloc}${normalizedPath}`;
};
