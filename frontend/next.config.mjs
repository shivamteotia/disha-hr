// Proxy /api to FastAPI so the session cookie stays same-origin (works from phones on the LAN too).
export default {
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${process.env.API_URL || 'http://127.0.0.1:8000'}/api/:path*` }];
  },
};
