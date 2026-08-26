import React, { useState } from "react";
import { Field } from "./fields.jsx";
import { useSubmitFlow } from "./useSubmitFlow.js";
import { BotBlock, ErrorSummary, Toast } from "./Feedback.jsx";

/**
 * Greenhouse-shaped form: `#application` wrapper, `span.asterisk` required
 * markers, an "expand all" demographic section, and (for the select2 case)
 * selects rendered behind a select2-style widget with the real <select>
 * visually hidden (select2 pattern: keep the select in the DOM as the data
 * source, style it away, and sync a div-based dropdown to it).
 */
function Select2Field({ field }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  return (
    <div className="field select2-field" data-field-key={field.key}>
      <label htmlFor={field.key}>
        {field.label}
        {field.required ? <span className="asterisk">*</span> : null}
      </label>
      {/* real select kept in DOM (data source), hidden like select2 does */}
      <select
        id={field.key}
        name={field.key}
        className="select2-hidden-accessible"
        style={{ position: "absolute", width: 1, height: 1, opacity: 0 }}
        value={value}
        required={field.required || undefined}
        onChange={(e) => setValue(e.target.value)}
      >
        <option value="" disabled>
          Select...
        </option>
        {field.options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
      <div
        className="select2-container"
        role="combobox"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <span className="select2-selection__rendered">
          {value || "Select..."}
        </span>
      </div>
      {open && (
        <ul className="select2-dropdown">
          {field.options.map((o) => (
            <li
              key={o}
              className="select2-results__option"
              onClick={() => {
                setValue(o);
                setOpen(false);
              }}
            >
              {o}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function GreenhousePage({ caseId, def }) {
  const [expanded, setExpanded] = useState(false);
  const { phase, error, extraField, handleSubmit } = useSubmitFlow("greenhouse", caseId);

  if (phase === "blocked") return <BotBlock />;

  const demographics = def.fields.filter((f) =>
    ["veteran_status", "disability_status", "gender"].includes(f.key)
  );
  const main = def.fields.filter((f) => !demographics.includes(f));

  return (
    <div className="ats-greenhouse">
      <h1>{def.title}</h1>
      <div id="application">
        <form onSubmit={handleSubmit}>
          {main.map((f) =>
            def.select2 && f.type === "select" ? (
              <Select2Field key={f.key} field={f} />
            ) : (
              <Field key={f.key} field={f} />
            )
          )}
          {demographics.length > 0 && (
            <div className="demographic-section">
              <button
                type="button"
                className="expand_all"
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? "Collapse" : "Expand"} voluntary self-identification
              </button>
              {expanded &&
                demographics.map((f) =>
                  def.select2 && f.type === "select" ? (
                    <Select2Field key={f.key} field={f} />
                  ) : (
                    <Field key={f.key} field={f} />
                  )
                )}
            </div>
          )}
          {extraField && <Field key={extraField.key} field={extraField} />}
          <input type="submit" value="Submit Application" />
        </form>
      </div>
      <ErrorSummary ats="greenhouse" error={error} />
      {phase === "toast" && <Toast ats="greenhouse" />}
    </div>
  );
}
