import type { NextConfig } from "next";
import createMDX from "@next/mdx";

const withMDX = createMDX({
  options: {
    // String form (not import) is required by Turbopack — the config must be
    // serializable across the worker boundary.
    remarkPlugins: [["remark-gfm", {}]],
  },
});

const nextConfig: NextConfig = {
  pageExtensions: ["ts", "tsx", "js", "jsx", "md", "mdx"],
  allowedDevOrigins: ["nyc-transit.vannala.org"],
};

export default withMDX(nextConfig);
