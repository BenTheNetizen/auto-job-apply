import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirnameFix = import.meta.dirname ?? path.dirname(fileURLToPath(import.meta.url));

/**
 * Load the gold label file for an applicationId ("ashby/basic" ->
 * gold/ashby__basic.json). Returns null when the case has no gold file.
 */
function loadGold(applicationId) {
  const safe = String(applicationId).replace(/[^a-z0-9/_-]/gi, "");
  const goldFile = path.resolve(__dirnameFix, "gold", safe.replace("/", "__") + ".json");
  try {
    return JSON.parse(fs.readFileSync(goldFile, "utf-8"));
  } catch {
    return null;
  }
}

function json(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(body));
}

const BOT_BLOCK_BODY =
  "<html><body><h1>Verify you are human</h1>" +
  "<p>Our systems detected unusual traffic from your network. " +
  "Please verify you are human to continue.</p></body></html>";

/**
 * Dev-server plugin: POST /submit behaves per the case's gold JSON:
 *  - bot_block: HTTP 403 generic block page (never records)
 *  - reject_rules: field value not matching the rule pattern -> HTTP 422
 *  - progressive_field: missing/empty in the payload -> HTTP 422 naming the
 *    missing field (the page re-renders with it; a corrected POST succeeds)
 *  - otherwise: record to submissions/<ats>__<case>.json and answer 200 with
 *    the case's confirmation_style so the page toasts or redirects.
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
          let payload;
          try {
            payload = JSON.parse(body);
          } catch (err) {
            return json(res, 400, { error: String(err) });
          }
          const gold = loadGold(payload.applicationId);

          if (gold?.bot_block) {
            res.statusCode = 403;
            res.setHeader("Content-Type", "text/html");
            res.end(BOT_BLOCK_BODY);
            return;
          }

          const fields = payload.fields || {};

          for (const rule of gold?.reject_rules || []) {
            const value = fields[rule.field];
            const text = Array.isArray(value) ? value.join("|") : String(value ?? "");
            if (!new RegExp(rule.pattern).test(text)) {
              return json(res, 422, { error: rule.error, field: rule.field });
            }
          }

          const progressive = gold?.progressive_field;
          if (progressive) {
            const value = fields[progressive.key];
            const empty =
              value === undefined ||
              value === null ||
              value === "" ||
              (Array.isArray(value) && value.length === 0);
            if (empty) {
              return json(res, 422, {
                error: `Missing required field: ${progressive.label}`,
                missing_field: progressive,
              });
            }
          }

          const dir = path.resolve(__dirnameFix, "submissions");
          fs.mkdirSync(dir, { recursive: true });
          const safe = String(payload.applicationId)
            .replace(/[^a-z0-9/_-]/gi, "")
            .replace("/", "__");
          fs.writeFileSync(
            path.join(dir, `${safe}.json`),
            JSON.stringify(payload, null, 2)
          );
          json(res, 200, {
            ok: true,
            applicationId: payload.applicationId,
            confirmation_style: gold?.confirmation_style || "toast",
          });
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
