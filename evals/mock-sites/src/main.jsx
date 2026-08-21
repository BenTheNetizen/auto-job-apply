import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Routes, Route, Link, useParams } from "react-router-dom";
import { CASES } from "./cases.js";
import AshbyPage from "./AshbyPage.jsx";
import GreenhousePage from "./GreenhousePage.jsx";
import LeverPage from "./LeverPage.jsx";
import "./styles.css";

const PAGES = { ashby: AshbyPage, greenhouse: GreenhousePage, lever: LeverPage };

function CaseRoute({ ats }) {
  const { caseId } = useParams();
  const def = CASES[ats]?.[caseId];
  if (!def) return <div>Unknown case: {ats}/{caseId}</div>;
  const Page = PAGES[ats];
  return <Page caseId={caseId} def={def} />;
}

function Home() {
  return (
    <div>
      <h1>Mock ATS Sites</h1>
      {Object.entries(CASES).map(([ats, cases]) => (
        <div key={ats}>
          <h2>{ats}</h2>
          <ul>
            {Object.keys(cases).map((c) => (
              <li key={c}>
                <Link to={`/${ats}/${c}`}>
                  /{ats}/{c}
                </Link>{" "}
                — {cases[c].title}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

createRoot(document.getElementById("root")).render(
  <BrowserRouter>
    <Routes>
      <Route path="/" element={<Home />} />
      <Route path="/ashby/:caseId" element={<CaseRoute ats="ashby" />} />
      <Route path="/greenhouse/:caseId" element={<CaseRoute ats="greenhouse" />} />
      <Route path="/lever/:caseId" element={<CaseRoute ats="lever" />} />
    </Routes>
  </BrowserRouter>
);
