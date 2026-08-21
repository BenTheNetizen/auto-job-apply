/**
 * Programmatic dev-server entry for the mock ATS sites.
 *
 * Used by evals/run_evals.py: the CLI-driven `vite` boot path was observed to
 * miss the submit-recorder middleware in this repo (404 on POST /submit),
 * while vite's createServer API reliably installs plugin middleware. This
 * entry keeps the run hermetic: one process, printed port, SIGTERM-friendly.
 *
 * Usage: node server.mjs [--port N]
 * Env:   PORT overrides (flag wins).
 */
import { createServer } from "vite";
import conf from "./vite.config.js";

const args = process.argv.slice(2);
const flagIdx = args.indexOf("--port");
const port = Number(
  flagIdx !== -1 ? args[flagIdx + 1] : process.env.PORT || 5173,
);

const server = await createServer({
  configFile: false,
  root: process.cwd(),
  plugins: conf.plugins,
  server: { port, strictPort: true },
});
await server.listen();
server.printUrls();
console.log(`MOCK_SITES_PORT=${port}`);

async function shutdown() {
  try {
    await server.close();
  } finally {
    process.exit(0);
  }
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
