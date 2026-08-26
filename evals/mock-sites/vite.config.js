import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirnameFix = import.meta.dirname ?? path.dirname(fileURLToPath(import.meta.url));

/**
 * Dev-server plugin: POST /submit behaves per the case's gold config
 * (gold/<ats>__<case>.json), then records successful payloads to
 * submissions/<ats>__<case>.json. Body: { applicationId: "ashby/basic", fields }.
 *
 * Behavior keys (all optional, read from gold):
 * - confirmation_style: "toast" (default) | "redirect" — echoed to the client
 *     on success so the page can pick inline toast vs. confirmation-page nav.
 * - reject_rules: [{ field, pattern, error }] — first field value failing the
 *     regex returns 422 { error, field }.
 * - bot_block: true — every POST returns 403 with a generic block message.
 * - progressive_field: { key, label, type, required, options? } — POSTs missing
 *     this field return 422 { error, missing_field }; once present, the
 *     submission records normally (progressive disclosure).
 */
function submitRecorder() {
  const goldDir = path.resolve(__dirnameFix, "gold");

  function loadGold(applicationId) {
    const safe = String(applicationId ?? "").replace(/[^a-z0-9/_-]/gi, "");
    if (!safe.includes("/")) return {};
    try {
      return JSON.parse(
        fs.readFileSync(path.join(goldDir, `${safe.replace("/", "__")}.json`), "utf-8")
      );
    } catch {
      return {};
    }
  }

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
          const json = (code, obj) => {
            res.statusCode = code;
            res.setHeader("Content-Type", "application/json");
            res.end(JSON.stringify(obj));
          };
          try {
            const payload = JSON.parse(body);
            const gold = loadGold(payload.applicationId);
            const fields = payload.fields || {};

            // Bot detection: generic block page.
            if (gold.bot_block) {
              return json(403, {
                error: "Traffic blocked. Verify you are human.",
                blocked: true,
              });
            }

            // Progressive disclosure: first POST without the extra required
            // field is rejected and names it; re-submission with it succeeds.
            if (gold.progressive_field) {
              const pf = gold.progressive_field;
              const value = fields[pf.key];
              const missing =
                value === undefined ||
                value === null ||
                value === "" ||
                (Array.isArray(value) && value.length === 0);
              if (missing) {
                return json(422, {
                  error: `Missing required field: ${pf.label}`,
                  missing_field: pf,
                });
              }
            }

            // Server-side validation rules (e.g. malformed date).
            for (const rule of gold.reject_rules || []) {
              const value = fields[rule.field];
              const str = value == null ? "" : String(value);
              if (!new RegExp(rule.pattern).test(str)) {
                return json(422, { error: rule.error, field: rule.field });
              }
            }

            // Success: record the payload for the eval runner.
            const dir = path.resolve(__dirnameFix, "submissions");
            fs.mkdirSync(dir, { recursive: true });
            const safe = String(payload.applicationId)
              .replace(/[^a-z0-9/_-]/gi, "")
              .replace("/", "__");
            fs.writeFileSync(
              path.join(dir, `${safe}.json`),
              JSON.stringify(payload, null, 2)
            );
            return json(200, {
              ok: true,
              applicationId: payload.applicationId,
              confirmation_style: gold.confirmation_style || "toast",
            });
          } catch (err) {
            json(400, String(err));
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
