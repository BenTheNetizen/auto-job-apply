import React, { useState } from "react";
import { Field } from "./fields.jsx";
import { collectFields, postSubmission } from "./submit.js";

/**
 * Ashby-shaped form: plain <form> root, cookie banner, labels with "*" for
 * required, submit button reads "Submit Application".
 */
export default function AshbyPage({ caseId, def }) {
  const [showBanner, setShowBanner] = useState(true);
  const [result, setResult] = useState(null);

  async function onSubmit(e) {
    e.preventDefault();
    const fields = collectFields(e.target);
    const res = await postSubmission("ashby", caseId, fields);
    setResult(res);
  }

  return (
    <div className="ats-ashby">
      {showBanner && (
        <div className="cookie-banner">
          <span>We use cookies to improve your experience.</span>
          <button type="button" onClick={() => setShowBanner(false)}>
            Accept
          </button>
        </div>
      )}
      <h1>{def.title}</h1>
      <form onSubmit={onSubmit}>
        {def.fields.map((f) => (
          <Field key={f.key} field={f} />
        ))}
        <button type="submit">Submit Application</button>
      </form>
      {result && (
        <div className="confirmation" data-testid="confirmation">
          Application received. Confirmation id: {result.applicationId}
        </div>
      )}
    </div>
  );
}
