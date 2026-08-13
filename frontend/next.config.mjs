/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output bundles a minimal Node server + traced node_modules into
  // .next/standalone, making the Docker image ~50MB instead of ~500MB.
  output: "standalone",
  // next dev binds as "localhost"; Cursor / browsers often hit 127.0.0.1.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
  async rewrites() {
    // Prod sits behind Caddy/nginx which already routes /api to the backend.
    // In next dev, proxy so the browser only needs the frontend port.
    if (process.env.NODE_ENV === "production") return [];
    const backend = process.env.BACKEND_URL || "http://127.0.0.1:8010";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/healthz", destination: `${backend}/healthz` },
      { source: "/readyz", destination: `${backend}/readyz` },
    ];
  },
};

export default nextConfig;
