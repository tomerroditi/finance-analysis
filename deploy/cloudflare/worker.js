/**
 * Cloudflare Worker fronting the Finance Analysis demo.
 *
 * Static assets (the React build) are served directly by the Workers assets
 * layer — requests only reach this script for the backend paths listed in
 * wrangler.jsonc `run_worker_first`. Those are proxied to a Cloudflare
 * Container running the FastAPI app (see deploy/cloudflare/Dockerfile).
 *
 * Deliberately dependency-free: the container lifecycle is driven through the
 * raw Durable Object container API (`this.ctx.container`) instead of the
 * @cloudflare/containers package, so no root package.json / lockfile is
 * needed to deploy.
 */

import { DurableObject } from "cloudflare:workers";

const CONTAINER_PORT = 8000;
// First request after a cold start (or after the container went to sleep)
// must wait for uvicorn to boot and seed the demo DB. Poll until then.
const STARTUP_DEADLINE_MS = 120_000;
const RETRY_INTERVAL_MS = 1_000;

const BACKEND_PATHS = /^\/(api\/|health$|docs$|redoc$|openapi\.json$)/;

export class FinanceBackend extends DurableObject {
	async fetch(request) {
		const container = this.ctx.container;
		if (!container) {
			return new Response("Container runtime unavailable", { status: 503 });
		}
		if (!container.running) {
			// Internet egress is needed for the GitHub releases probe in
			// backend.services.update_service.
			container.start({ enableInternet: true });
		}

		const url = new URL(request.url);
		const target = `http://container${url.pathname}${url.search}`;
		// Buffer the body so the request can be retried while uvicorn boots
		// (a streamed body is consumed by the first failed attempt).
		const body = ["GET", "HEAD"].includes(request.method)
			? undefined
			: await request.arrayBuffer();

		const port = container.getTcpPort(CONTAINER_PORT);
		const deadline = Date.now() + STARTUP_DEADLINE_MS;
		for (;;) {
			try {
				return await port.fetch(target, {
					method: request.method,
					headers: request.headers,
					body,
				});
			} catch (err) {
				if (Date.now() >= deadline) {
					console.error("container did not become ready", err);
					return new Response(
						"The demo backend is starting up — please retry in a few seconds.",
						{ status: 503 },
					);
				}
				await new Promise((resolve) => setTimeout(resolve, RETRY_INTERVAL_MS));
			}
		}
	}
}

export default {
	async fetch(request, env) {
		const { pathname } = new URL(request.url);
		if (BACKEND_PATHS.test(pathname)) {
			// Single shared demo instance for all visitors.
			const stub = env.BACKEND.get(env.BACKEND.idFromName("demo"));
			return stub.fetch(request);
		}
		return env.ASSETS.fetch(request);
	},
};
