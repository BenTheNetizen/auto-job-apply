import React from "react";
import { Field } from "./fields.jsx";
import { useSubmitFlow } from "./useSubmitFlow.js";
import { BotBlock, ErrorSummary, Toast } from "./Feedback.jsx";

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
  const { phase, error, extraField, handleSubmit } = useSubmitFlow("lever", caseId);

  if (phase === "blocked") return <BotBlock />;

  return (
    <div className="ats-lever">
      <h1>{def.title}</h1>
      <div className="application-form">
        <form onSubmit={handleSubmit}>
          {def.accordion
            ? def.sections.map((s) => (
                <AccordionSection
                  key={s.heading}
                  heading={s.heading}
                  fields={s.fields}
                />
              ))
            : def.fields.map((f) => <Field key={f.key} field={f} />)}
          {extraField && <Field key={extraField.key} field={extraField} />}
          <button type="submit">Submit</button>
        </form>
      </div>
      <ErrorSummary ats="lever" error={error} />
      {phase === "toast" && <Toast ats="lever" />}
    </div>
  );
}
