import React, { useState } from "react";
import { Field } from "./fields.jsx";
import { collectFields, postSubmission } from "./submit.js";

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
  const [result, setResult] = useState(null);

  async function onSubmit(e) {
    e.preventDefault();
    const fields = collectFields(e.target);
    const res = await postSubmission("lever", caseId, fields);
    setResult(res);
  }

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
            : def.fields.map((f) => <Field key={f.key} field={f} />)}
          <button type="submit">Submit</button>
        </form>
      </div>
      {result && (
        <div className="confirmation" data-testid="confirmation">
          Application received. Confirmation id: {result.applicationId}
        </div>
      )}
    </div>
  );
}
