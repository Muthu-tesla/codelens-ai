import type { NextConfig } from "next";

const isShowcase =
  process.env.NEXT_PUBLIC_SHOWCASE_MODE === "true" ||
  process.env.NEXT_PUBLIC_SHOWCASE_MODE === "1";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig: NextConfig = {
  /* config options here */
  output: isShowcase ? "export" : undefined,
  basePath: basePath || undefined,
  // Partial prefetching / component caching only apply when server runtime is present
  cacheComponents: isShowcase ? undefined : true,
  partialPrefetching: isShowcase ? undefined : true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
