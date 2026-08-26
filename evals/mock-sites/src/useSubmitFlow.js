import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { collectFields, postSubmission } from "./submit.js";

/**
 * Shared submit flow for all three ATS pages. Handles:
 * - 403 / blocked → bot-block view
 * - 422 → error summary; when the server names a missing_field (progressive
 *   disclosure) the field is appended to the rendered form for re-submission
 * - success + confirmation_style "redirect" → navigate to the confirmation
 *   route; otherwise show the inline toast (existing behavior)
 */
export function useSubmitFlow(ats, caseId) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [blocked, setBlocked] = useState(false);
  const [extraFields, setExtraFields] = useState([]);
  const navigate = useNavigate();

  async function onSubmit(e) {
    e.preventDefault();
    const fields = collectFields(e.target);
    const res = await postSubmission(ats, caseId, fields);
    if (res.status === 403 || res.blocked) {
      setBlocked(true);
      return;
    }
    if (res.status === 422) {
      if (res.missing_field) {
        setExtraFields((prev) =>
          prev.some((f) => f.key === res.missing_field.key)
            ? prev
            : [...prev, res.missing_field]
        );
      }
      setError(res);
      return;
    }
    setError(null);
    if (res.confirmation_style === "redirect") {
      navigate(`/${ats}/${caseId}/confirmation`);
      return;
    }
    setResult(res);
  }

  return { result, error, blocked, extraFields, onSubmit };
}
