import React from "react";

/**
 * Shared feedback components for the ATS pages: toast banner, validation
 * error summary, bot-detection block page, and the standalone confirmation
 * view used by redirect-style cases.
 *
 * The texts deliberately hit the filler's generic confirmation markers
 * ("application submitted", "thank you", "we'll be in touch") and its error
 * markers ("error submitting", "submission failed", "something went wrong")
 * so both the current generic detector and the per-ATS confirmation-detection
 * leaf have realistic, machine-checkable signals.
 */

const SUCCESS_TEXT = {
  ashby: "Application submitted. Thank you for applying — we've received your application.",
  greenhouse: "Application submitted — we'll be in touch.",
  lever: "Thank you for applying. We'll be in touch.",
};

const ERROR_LEAD = {
  ashby: "Error submitting application",
  greenhouse: "There was a problem with your application",
  lever: "Something went wrong while submitting your application",
};

export function Toast({ ats }) {
  return (
    <div className={`toast toast-${ats}`} data-testid="confirmation" role="status">
      {SUCCESS_TEXT[ats]}
    </div>
  );
}

export function ErrorSummary({ ats, error }) {
  if (!error) return null;
  return (
    <div className={`error-summary error-${ats}`} role="alert">
      {ERROR_LEAD[ats]}: {error}
    </div>
  );
}

export function BotBlock() {
  return (
    <div className="bot-block" role="alert">
      <h1>Verify you are human</h1>
      <p>
        Our systems detected unusual traffic from your network. Please verify
        you are human to continue.
      </p>
      <div className="captcha-box">
        <span className="captcha-checkbox" /> I&apos;m not a robot
      </div>
    </div>
  );
}

export function ConfirmationView({ ats, title }) {
  return (
    <div className={`confirmation-page confirmation-${ats}`} data-testid="confirmation">
      <h1>{ats === "lever" ? "Thank you for applying" : "Application submitted"}</h1>
      <p>
        {SUCCESS_TEXT[ats]} {title ? `(${title})` : ""}
      </p>
    </div>
  );
}
