import React, { useState } from "react";
import { Field } from "./fields.jsx";
import { useSubmitFlow } from "./useSubmitFlow.js";
import { BotBlock, ErrorSummary, Toast } from "./Feedback.jsx";

/**
 * Ashby-shaped form: plain <form> root, cookie banner, labels with "*" for
 * required, submit button reads "Submit Application". Submission outcomes
 * (toast / redirect / validation error / bot block / progressive field) are
 * driven by the case's gold JSON via useSubmitFlow.
 */
export default function AshbyPage({ caseId, def }) {
  const [showBanner, setShowBanner] = useState(true);
  const { phase, error, extraField, handleSubmit } = useSubmitFlow("ashby", caseId);

  if (phase === "blocked") return <BotBlock />;

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
      <form onSubmit={handleSubmit}>
        {def.fields.map((f) => (
          <Field key={f.key} field={f} />
        ))}
        {extraField && <Field key={extraField.key} field={extraField} />}
        <button type="submit">Submit Application</button>
      </form>
      <ErrorSummary ats="ashby" error={error} />
      {phase === "toast" && <Toast ats="ashby" />}
    </div>
  );
}
