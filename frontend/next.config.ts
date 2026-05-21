import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Allow Azure Blob Storage images
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "squawksmlstorage.blob.core.windows.net",
      },
    ],
  },
  // Production API URL will be set via NEXT_PUBLIC_API_URL env var
};

export default nextConfig;
