/**
 * Collect field values from a submitted <form> into a flat object.
 * - text/textarea/select/date: the value
 * - radio: the checked value (or "" if none)
 * - checkbox-group: array of checked values
 * - file: the file name (contents aren't uploaded to the mock endpoint)
 */
export function collectFields(form) {
  const out = {};
  const seen = new Set();
  for (const el of form.elements) {
    if (!el.name || seen.has(el.name)) continue;
    seen.add(el.name);
    if (el.type === "radio") {
      const checked = form.querySelector(`input[name="${el.name}"]:checked`);
      out[el.name] = checked ? checked.value : "";
    } else if (el.type === "checkbox") {
      out[el.name] = Array.from(
        form.querySelectorAll(`input[name="${el.name}"]:checked`)
      ).map((c) => c.value);
    } else if (el.type === "file") {
      out[el.name] = el.files && el.files.length ? el.files[0].name : "";
    } else {
      out[el.name] = el.value;
    }
  }
  return out;
}

/**
 * POST the submission to the dev-server plugin endpoint. Never throws:
 * returns { status, ok, ...body } so pages can drive toast vs. redirect
 * confirmations, 422 validation/progressive flows, and 403 bot blocks.
 */
export async function postSubmission(ats, caseId, fields) {
  const applicationId = `${ats}/${caseId}`;
  const res = await fetch("/submit", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ applicationId, fields }),
  });
  let body = {};
  try {
    body = await res.json();
  } catch {
    /* non-JSON body (shouldn't happen) */
  }
  return { status: res.status, ok: res.ok, ...body };
}
