import React, { useState } from "react";
import { Field } from "./fields.jsx";
import { useSubmitFlow } from "./useSubmitFlow.js";
import { ErrorSummary, BotBlock, ConfirmationToast } from "./Feedback.jsx";

/**
 * Ashby-shaped form: plain <form> root, cookie banner, labels with "*" for
 * required, submit button reads "Submit Application".
 */
export default function AshbyPage({ caseId, def }) {
  const [showBanner, setShowBanner] = useState(true);
  const { result, error, blocked, extraFields, onSubmit } = useSubmitFlow(
    "ashby",
    caseId
  );

  const fields = def.fields.concat(extraFields);

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
        {fields.map((f) => (
          <Field key={f.key} field={f} />
        ))}
        <button type="submit">Submit Application</button>
      </form>
      <ErrorSummary ats="ashby" error={error} />
      {blocked && <BotBlock />}
      <ConfirmationToast result={result} />
    </div>
  );
}
