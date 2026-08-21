import React from "react";

/**
 * Shared field renderers. Each renders a real DOM element with a <label>
 * whose text content matches the field label (plugins find fields by label).
 * `required` fields show a "*" marker in/after the label and carry the
 * `required` attribute where the element type supports it.
 */

export function TextField({ field }) {
  return (
    <div className="field" data-field-key={field.key}>
      <label htmlFor={field.key}>
        {field.label}
        {field.required ? " *" : ""}
      </label>
      <input
        id={field.key}
        name={field.key}
        type="text"
        required={field.required || undefined}
      />
    </div>
  );
}

export function TextareaField({ field }) {
  return (
    <div className="field" data-field-key={field.key}>
      <label htmlFor={field.key}>
        {field.label}
        {field.required ? " *" : ""}
      </label>
      <textarea
        id={field.key}
        name={field.key}
        rows={5}
        required={field.required || undefined}
      />
    </div>
  );
}

export function SelectField({ field }) {
  return (
    <div className="field" data-field-key={field.key}>
      <label htmlFor={field.key}>
        {field.label}
        {field.required ? " *" : ""}
      </label>
      <select
        id={field.key}
        name={field.key}
        required={field.required || undefined}
        defaultValue=""
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
    </div>
  );
}

export function RadioField({ field }) {
  return (
    <fieldset className="field" data-field-key={field.key}>
      <legend>
        {field.label}
        {field.required ? " *" : ""}
      </legend>
      {field.options.map((o) => (
        <label key={o}>
          <input
            type="radio"
            name={field.key}
            value={o}
            required={field.required || undefined}
          />
          {o}
        </label>
      ))}
    </fieldset>
  );
}

export function CheckboxGroupField({ field }) {
  return (
    <fieldset className="field" data-field-key={field.key}>
      <legend>
        {field.label}
        {field.required ? " *" : ""}
      </legend>
      {field.options.map((o) => (
        <label key={o}>
          <input type="checkbox" name={field.key} value={o} />
          {o}
        </label>
      ))}
    </fieldset>
  );
}

export function DateField({ field }) {
  return (
    <div className="field" data-field-key={field.key}>
      <label htmlFor={field.key}>
        {field.label}
        {field.required ? " *" : ""}
      </label>
      <input
        id={field.key}
        name={field.key}
        type="date"
        required={field.required || undefined}
      />
    </div>
  );
}

export function FileField({ field }) {
  return (
    <div className="field" data-field-key={field.key}>
      <label htmlFor={field.key}>
        {field.label}
        {field.required ? " *" : ""}
      </label>
      <input
        id={field.key}
        name={field.key}
        type="file"
        required={field.required || undefined}
      />
    </div>
  );
}

const RENDERERS = {
  text: TextField,
  textarea: TextareaField,
  select: SelectField,
  radio: RadioField,
  "checkbox-group": CheckboxGroupField,
  date: DateField,
  file: FileField,
};

export function Field({ field }) {
  const R = RENDERERS[field.type];
  if (!R) return <div className="field">unknown field type: {field.type}</div>;
  return <R field={field} />;
}
