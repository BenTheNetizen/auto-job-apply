import React, { useState } from "react";
import { Field } from "./fields.jsx";
import { useSubmitFlow } from "./useSubmitFlow.js";
import { ErrorSummary, BotBlock, ConfirmationToast } from "./Feedback.jsx";

/**
 * Lever-shaped form: `div.application-form` wrapper, optional accordion
 * sections behind `.toggle` headers that must be clicked to reveal fields.
 */
function AccordionSection({ heading, fields }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="accordion-section">
      <div className="toggle" onClick={() => setOpen(!open)}>
        {open ? "▾" : "▸"} {heading}
      </div>
      {open && (
        <div className="accordion-body">
          {fields.map((f) => (
            <Field key={f.key} field={f} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function LeverPage({ caseId, def }) {
  const { result, error, blocked, extraFields, onSubmit } = useSubmitFlow(
    "lever",
    caseId
  );

  return (
    <div className="ats-lever">
      <h1>{def.title}</h1>
      <div className="application-form">
        <form onSubmit={onSubmit}>
          {def.accordion
            ? def.sections.map((s) => (
                <AccordionSection
                  key={s.heading}
                  heading={s.heading}
                  fields={s.fields}
                />
              ))
            : def.fields.concat(extraFields).map((f) => <Field key={f.key} field={f} />)}
          <button type="submit">Submit</button>
        </form>
      </div>
      <ErrorSummary ats="lever" error={error} />
      {blocked && <BotBlock />}
      <ConfirmationToast result={result} />
    </div>
  );
}
