import { useEffect, useState } from "react";
import { Sidebar, type PageKey } from "./components/Sidebar";
import { EntityPicker } from "./components/EntityPicker";
import { DailyDashboard } from "./pages/DailyDashboard";
import { RecommendationsPage } from "./pages/RecommendationsPage";
import { ConversationPanel } from "./pages/ConversationPanel";
import { AIInsightsPanel } from "./pages/AIInsightsPanel";
import { ResearchTab } from "./pages/ResearchTab";
import { listCompanies, listPeople } from "./lib/api";
import type { EntityRef } from "./lib/types";

export default function App() {
  const [page, setPage] = useState<PageKey>("dashboard");
  const [people, setPeople] = useState<EntityRef[]>([]);
  const [companies, setCompanies] = useState<EntityRef[]>([]);
  const [personId, setPersonId] = useState<string>();
  const [companyId, setCompanyId] = useState<string>();

  useEffect(() => {
    listPeople().then((ps) => {
      setPeople(ps);
      setPersonId((cur) => cur ?? ps[0]?.id);
    });
    listCompanies().then((cs) => {
      setCompanies(cs);
      setCompanyId((cur) => cur ?? cs[0]?.id);
    });
  }, []);

  function openPerson(id: string) {
    setPersonId(id);
    const p = people.find((x) => x.id === id);
    if (p?.companyName) {
      const match = companies.find((c) => c.name === p.companyName);
      if (match) setCompanyId(match.id);
    }
    setPage("conversation");
  }

  const selectedPerson = people.find((p) => p.id === personId);
  const selectedCompany = companies.find((c) => c.id === companyId);

  return (
    <div className="flex h-full">
      <Sidebar page={page} onNavigate={setPage} />

      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto px-8 py-6">
          {page === "dashboard" && <DailyDashboard onOpenPerson={openPerson} />}
          {page === "recommendations" && <RecommendationsPage onOpenPerson={openPerson} />}

          {page === "conversation" && (
            <div>
              <div className="mb-4">
                <EntityPicker label="Person" entities={people} selectedId={personId} onSelect={setPersonId} />
              </div>
              {selectedPerson ? (
                <ConversationPanel person={selectedPerson} />
              ) : (
                <p className="text-sm" style={{ color: "var(--ink-faint)" }}>Loading people…</p>
              )}
            </div>
          )}

          {page === "insights" && (
            <div>
              <div className="mb-4">
                <EntityPicker label="Company" entities={companies} selectedId={companyId} onSelect={setCompanyId} />
              </div>
              {selectedCompany ? (
                <AIInsightsPanel company={selectedCompany} />
              ) : (
                <p className="text-sm" style={{ color: "var(--ink-faint)" }}>Loading companies…</p>
              )}
            </div>
          )}

          {page === "research" && (
            <div>
              <div className="mb-4">
                <EntityPicker label="Company" entities={companies} selectedId={companyId} onSelect={setCompanyId} />
              </div>
              {selectedCompany ? (
                <ResearchTab company={selectedCompany} />
              ) : (
                <p className="text-sm" style={{ color: "var(--ink-faint)" }}>Loading companies…</p>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
