/**
 * Case catalog. Field keys here MUST match the gold labels in gold/<case>.json
 * and the expected answers are authored against the mock profile
 * (Taylor Wong <taylor.wong@agentmail.to>).
 *
 * Every case covers the flavor matrix; one case per ATS adds the "annoying"
 * behavior (select2-backed select for greenhouse, accordion for lever).
 */

const common = {
  fullName: { key: "full_name", label: "Full Name", type: "text", required: true },
  email: { key: "email", label: "Email", type: "text", required: true },
  phone: { key: "phone", label: "Phone", type: "text", required: false },
  linkedin: { key: "linkedin_url", label: "LinkedIn URL", type: "text", required: false },
  github: { key: "github_url", label: "GitHub URL", type: "text", required: false },
  website: { key: "website", label: "Personal Website", type: "text", required: false },
  resume: { key: "resume", label: "Resume", type: "file", required: true },
  coverLetter: {
    key: "cover_letter",
    label: "Cover Letter",
    type: "textarea",
    required: false,
  },
  whyFit: {
    key: "why_fit",
    label: "Why are you a good fit for this role?",
    type: "textarea",
    required: true,
  },
  startDate: {
    key: "start_date",
    label: "Earliest Start Date",
    type: "date",
    required: true,
  },
  workAuth: {
    key: "work_authorization",
    label: "Are you authorized to work in the United States?",
    type: "radio",
    required: true,
    options: ["Yes", "No"],
  },
  sponsorship: {
    key: "visa_sponsorship",
    label: "Will you now or in the future require visa sponsorship?",
    type: "radio",
    required: true,
    options: ["Yes", "No"],
  },
  veteran: {
    key: "veteran_status",
    label: "Veteran Status",
    type: "select",
    required: false,
    options: [
      "I am not a protected veteran",
      "I am a protected veteran",
      "I choose not to self-identify",
    ],
  },
  disability: {
    key: "disability_status",
    label: "Disability Status",
    type: "select",
    required: false,
    options: [
      "Yes, I have a disability",
      "No, I do not have a disability",
      "I do not wish to answer",
    ],
  },
  gender: {
    key: "gender",
    label: "Gender",
    type: "select",
    required: false,
    options: ["Male", "Female", "Non-binary", "I decline to self-identify"],
  },
  referralSource: {
    key: "referral_source",
    label: "How did you hear about us?",
    type: "select",
    required: true,
    options: ["Job board", "Referral", "Company website", "Recruiter", "Other"],
  },
  interests: {
    key: "interests",
    label: "Which areas interest you? (select all that apply)",
    type: "checkbox-group",
    required: false,
    options: ["Backend", "Frontend", "Infrastructure", "Machine Learning", "Product"],
  },
  relocation: {
    key: "relocation",
    label: "Are you willing to relocate?",
    type: "radio",
    required: true,
    options: ["Yes", "No"],
  },
  salary: {
    key: "salary_expectation",
    label: "Salary Expectation",
    type: "text",
    required: false,
  },
};

export const CASES = {
  ashby: {
    basic: {
      title: "Software Engineer — Acme Robotics (Ashby)",
      fields: [
        common.fullName,
        common.email,
        common.phone,
        common.resume,
        common.whyFit,
        common.workAuth,
        common.sponsorship,
      ],
    },
    screening: {
      title: "Backend Engineer — Dataflow Inc (Ashby)",
      fields: [
        common.fullName,
        common.email,
        common.linkedin,
        common.resume,
        common.startDate,
        common.referralSource,
        common.relocation,
        common.salary,
        common.whyFit,
      ],
    },
    demographics: {
      title: "Full-Stack Engineer — Nova Labs (Ashby)",
      fields: [
        common.fullName,
        common.email,
        common.resume,
        common.coverLetter,
        common.interests,
        common.veteran,
        common.disability,
        common.gender,
        common.whyFit,
      ],
    },
    // Confirmation-style / failure-mode cases (behavior configured in
    // gold/<case>.json; the page just follows the server response).
    redirect: {
      title: "Frontend Engineer — Signal Works (Ashby)",
      fields: [
        common.fullName,
        common.email,
        common.phone,
        common.resume,
        common.whyFit,
        common.workAuth,
        common.sponsorship,
      ],
    },
    "reject-format": {
      title: "QA Engineer — Proof Labs (Ashby)",
      fields: [
        common.fullName,
        common.email,
        common.phone,
        common.resume,
        common.whyFit,
        common.workAuth,
        common.sponsorship,
      ],
    },
    progressive: {
      title: "Platform Engineer — Vault Systems (Ashby)",
      fields: [
        common.fullName,
        common.email,
        common.phone,
        common.resume,
        common.whyFit,
        common.workAuth,
        common.sponsorship,
      ],
    },
  },
  greenhouse: {
    basic: {
      title: "Platform Engineer — Meridian Systems (Greenhouse)",
      fields: [
        common.fullName,
        common.email,
        common.phone,
        common.resume,
        common.whyFit,
        common.workAuth,
        common.sponsorship,
      ],
    },
    select2: {
      title: "ML Engineer — Cortex AI (Greenhouse)",
      select2: true,
      fields: [
        common.fullName,
        common.email,
        common.linkedin,
        common.resume,
        common.startDate,
        common.referralSource,
        common.veteran,
        common.disability,
        common.whyFit,
      ],
    },
    demographics: {
      title: "Site Reliability Engineer — Orbital Cloud (Greenhouse)",
      fields: [
        common.fullName,
        common.email,
        common.resume,
        common.interests,
        common.relocation,
        common.salary,
        common.veteran,
        common.disability,
        common.gender,
        common.whyFit,
      ],
    },
    toast: {
      title: "Support Engineer — Harbor Systems (Greenhouse)",
      fields: [
        common.fullName,
        common.email,
        common.phone,
        common.resume,
        common.whyFit,
        common.workAuth,
        common.sponsorship,
      ],
    },
    redirect: {
      title: "Growth Engineer — Northwind Commerce (Greenhouse)",
      fields: [
        common.fullName,
        common.email,
        common.phone,
        common.resume,
        common.whyFit,
        common.workAuth,
        common.sponsorship,
      ],
    },
    "reject-format": {
      title: "Data Platform Engineer — Ledgerline (Greenhouse)",
      fields: [
        common.fullName,
        common.email,
        common.resume,
        common.startDate,
        common.referralSource,
        common.whyFit,
      ],
    },
  },
  lever: {
    basic: {
      title: "Product Engineer — Lighthouse Analytics (Lever)",
      fields: [
        common.fullName,
        common.email,
        common.phone,
        common.resume,
        common.whyFit,
        common.workAuth,
        common.sponsorship,
      ],
    },
    accordion: {
      title: "Infrastructure Engineer — Beacon Networks (Lever)",
      accordion: true,
      sections: [
        {
          heading: "Personal Information",
          fields: [common.fullName, common.email, common.phone, common.linkedin],
        },
        {
          heading: "Application Materials",
          fields: [common.resume, common.coverLetter, common.whyFit],
        },
        {
          heading: "Screening Questions",
          fields: [common.workAuth, common.sponsorship, common.startDate, common.relocation],
        },
      ],
    },
    demographics: {
      title: "Data Engineer — Riverstone Data (Lever)",
      fields: [
        common.fullName,
        common.email,
        common.resume,
        common.interests,
        common.referralSource,
        common.veteran,
        common.disability,
        common.gender,
        common.whyFit,
      ],
    },
    toast: {
      title: "Solutions Engineer — Meadowbrook (Lever)",
      fields: [
        common.fullName,
        common.email,
        common.phone,
        common.resume,
        common.whyFit,
        common.workAuth,
        common.sponsorship,
      ],
    },
    redirect: {
      title: "Security Engineer — Sentinel Grid (Lever)",
      fields: [
        common.fullName,
        common.email,
        common.phone,
        common.resume,
        common.whyFit,
        common.workAuth,
        common.sponsorship,
      ],
    },
    "bot-detect": {
      title: "Cloud Engineer — Fortress Hosting (Lever)",
      fields: [
        common.fullName,
        common.email,
        common.phone,
        common.resume,
        common.whyFit,
        common.workAuth,
        common.sponsorship,
      ],
    },
  },
};
