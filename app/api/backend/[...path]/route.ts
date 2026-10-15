import { proxyBackend } from "@/lib/backend";

export const runtime = "nodejs";
type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, context: Context) {
  return proxyBackend(request, (await context.params).path);
}

export async function POST(request: Request, context: Context) {
  return proxyBackend(request, (await context.params).path);
}
