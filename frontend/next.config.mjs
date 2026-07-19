/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Standalone output bundles a minimal Node server + traced node_modules into
  // .next/standalone, making the Docker image ~50MB instead of ~500MB.
  output: "standalone",
};

export default nextConfig;
