import type { NextConfig } from "next";

const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL ?? "http://localhost:31031";

const nextConfig: NextConfig = {
  // Produce a fully static site under `web/out/` during `npm run build`.
  // This enables the backend to serve the UI on the same origin as `/api/*`.
  output: "export",

  // Emit `/route/index.html` so generic static servers can map directories.
  // (See FastAPI/Starlette `StaticFiles(html=True)` mount in the backend.)
  trailingSlash: true,

  // Static export cannot use Next's built-in image optimization server.
  images: { unoptimized: true },

  async rewrites() {
    // Keep frontend code same-origin (/api/...) while proxying to the backend
    // during local development and basic deployments.
    if (process.env.NEXT_DISABLE_BACKEND_PROXY === "1") {
      return [];
    }
    return [
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND_BASE_URL}/api/v1/:path*`,
      },
      {
        source: "/api/v2/:path*",
        destination: `${BACKEND_BASE_URL}/api/v2/:path*`,
      },
    ];
  },
};

export default nextConfig;
