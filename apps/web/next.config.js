/** @type {import('next').NextConfig} */
const nextConfig = {
  // The reel templates ship as TypeScript source from the workspace.
  transpilePackages: ['@content-lab/reel-templates'],
  // The render service runs Remotion's own webpack + headless Chrome; keep them out of
  // Next's server bundle and load them from node_modules at runtime.
  serverExternalPackages: ['@remotion/renderer', '@remotion/bundler'],
};
module.exports = nextConfig;
