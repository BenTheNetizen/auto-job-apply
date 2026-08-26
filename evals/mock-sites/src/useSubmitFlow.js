import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { collectFields, postSubmission } from "./submit.js";

/**
 * Shared submit flow for the three ATS pages. Handles every outcome the
 * dev server can produce (driven by the case's gold JSON):
 *
 *  - 200 + confirmation_style "toast"    -> phase "toast" (inline banner)
 *  - 200 + confirmation_style "redirect" -> navigate to /<ats>/<case>/confirmation
 *  - 422 (validation)                    -> error summary; when the payload
 *    carries missing_field (progressive disclosure) the field is appended to
 *    the form via ``extraField`` for the re-submission attempt
 *  - 403 (bot_block)                     -> phase "blocked" (block page)
 */
export function useSubmitFlow(ats, caseId) {
  const [phase, setPhase] = useState("form"); // form | toast | blocked
  const [error, setError] = useState(null);
  const [extraField, setExtraField] = useState(null);
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    const fields = collectFields(e.target);
    const res = await postSubmission(ats, caseId, fields);
    if (res.status === 403) {
      setPhase("blocked");
      return;
    }
    if (res.status === 422) {
      if (res.missing_field) setExtraField(res.missing_field);
      setError(res.error || "Submission rejected");
      return;
    }
    if (res.ok) {
      setError(null);
      if (res.confirmation_style === "redirect") {
        navigate(`/${ats}/${caseId}/confirmation`);
      } else {
        setPhase("toast");
      }
      return;
    }
    setError(res.error || `submit failed: ${res.status}`);
  }

  return { phase, error, extraField, handleSubmit };
}
