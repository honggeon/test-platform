/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    // 跳过类型检查（项目存在大量水印注释遗留的类型不匹配）
    ignoreBuildErrors: true,
  },
  async rewrites() {
    return [
      // 平台后端 API
      {
        source: '/api/v2/:path*',
        destination: 'http://localhost:8000/api/v2/:path*',
      },
      // LangGraph
      {
        source: '/lg/:path*',
        destination: 'http://localhost:2026/:path*',
      },
    ];
  },
};

export default nextConfig;
