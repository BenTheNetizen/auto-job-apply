import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirnameFix = import.meta.dirname ?? path.dirname(fileURLToPath(import.meta.url));

/**
 * Dev-server plugin: POST /submit records the JSON payload to
 * submissions/<ats>__<case>.json so the eval runner can score what the
 * filler actually submitted. Body: { applicationId: "ashby/basic", fields }.
 */
function submitRecorder() {
  return {
    name: "submit-recorder",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url || !req.url.startsWith("/submit")) return next();
        if (req.method !== "POST") {
          res.statusCode = 405;
          res.end("method not allowed");
          return;
        }
        let body = "";
        req.on("data", (c) => (body += c));
        req.on("end", () => {
          try {
            const payload = JSON.parse(body);
            const dir = path.resolve(__dirnameFix, "submissions");
            fs.mkdirSync(dir, { recursive: true });
            const safe = String(payload.applicationId).replace(/[^a-z0-9/_-]/gi, "").replace("/", "__");
            fs.writeFileSync(
              path.join(dir, `${safe}.json`),
              JSON.stringify(payload, null, 2)
            );
            res.setHeader("Content-Type", "application/json");
            res.end(JSON.stringify({ ok: true, applicationId: payload.applicationId }));
          } catch (err) {
            res.statusCode = 400;
            res.end(String(err));
          }
        });
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), submitRecorder()],
  server: {
    port: 5173,
    strictPort: true,
  },
});
