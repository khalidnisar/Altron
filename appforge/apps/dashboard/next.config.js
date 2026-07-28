/** @type {import('next').NextConfig} */
const API_URL =
  process.env.APPFORGE_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  'http://api:8000';

const nextConfig = {
  output: 'standalone',
  reactStrictMode: true,
  // Proxy browser-side /api calls (CSV export, direct links) to the API service
  // so the client never needs to know the container hostname.
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${API_URL}/api/:path*` }];
  },
};

module.exports = nextConfig;
