import React from "react";

/**
 * ATS-shaped failure/success feedback UI shared by the three pages.
 * ErrorSummary mimics each ATS's server-rejection surface; ConfirmationToast
 * is the inline success banner (the "toast" confirmation style).
 */
export function ErrorSummary({ ats, error }) {
  if (!error) return null;
  if (ats === "greenhouse") {
    return (
      <div id="errorExplanation" className="flash-error" role="alert">
        <h2>There was a problem with your submission</h2>
        <p>{error.error}</p>
        {error.field && (
          <p className="field-error" data-error-field={error.field}>
            {error.field}
          </p>
        )}
      </div>
    );
  }
  return (
    <div className="error-summary" role="alert">
      <ul>
        <li>{error.error}</li>
      </ul>
      {error.field && (
        <span className="field-error" data-error-field={error.field}>
          {error.field}
        </span>
      )}
    </div>
  );
}

export function BotBlock() {
  return (
    <div className="bot-block" role="alert">
      <h2>Traffic blocked</h2>
      <p>Verify you are human.</p>
    </div>
  );
}

export function ConfirmationToast({ result }) {
  if (!result) return null;
  return (
    <div className="confirmation toast" data-testid="confirmation" role="status">
      Application submitted. Confirmation id: {result.applicationId}
    </div>
  );
}
