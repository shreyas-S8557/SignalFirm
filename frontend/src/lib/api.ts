import {
  fixtureCompanyRefs,
  fixtureDigest,
  fixturePeopleRefs,
  getCompanyInsights,
  getConversationSignals,
  getResearchJobs,
} from "./fixtures";
import type { CompanyInsights, ConversationSignal, DailyDigest, EntityRef, ResearchJob } from "./types";

// Point this at your running worker (see worker/README.md --
// `uvicorn scrapegraph_worker.api:app --reload`). Left unset, every call
// below falls back to realistic fixture data so the dashboard is fully
// browsable without a live worker/Twenty instance -- useful for reviewing
// the UI on its own, or as a design reference while wiring the real thing.
const API_BASE = import.meta.env.VITE_API_BASE_URL as string | undefined;

export const isLiveMode = Boolean(API_BASE);

async function get<T>(path: string): Promise<T> {
  if (!API_BASE) throw new Error("no API base configured");
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

export async function fetchDailyDigest(): Promise<{ data: DailyDigest; live: boolean }> {
  try {
    return { data: await get<DailyDigest>("/recommendations/daily-digest"), live: true };
  } catch {
    return { data: fixtureDigest, live: false };
  }
}

export async function fetchConversationSignals(personId: string): Promise<{ data: ConversationSignal[]; live: boolean }> {
  try {
    return { data: await get<ConversationSignal[]>(`/people/${personId}/conversation-signals`), live: true };
  } catch {
    return { data: getConversationSignals(personId), live: false };
  }
}

export async function fetchResearchJobs(companyId: string): Promise<{ data: ResearchJob[]; live: boolean }> {
  try {
    return { data: await get<ResearchJob[]>(`/companies/${companyId}/research-jobs`), live: true };
  } catch {
    return { data: getResearchJobs(companyId), live: false };
  }
}

export async function fetchCompanyInsights(companyId: string): Promise<{ data: CompanyInsights; live: boolean }> {
  try {
    return { data: await get<CompanyInsights>(`/companies/${companyId}/insights`), live: true };
  } catch {
    return { data: getCompanyInsights(companyId), live: false };
  }
}

// There's no "list all people/companies" endpoint in the worker (by
// design -- see api.py, it's a digest/analysis service, not a CRM proxy).
// The picker below stands in for what would otherwise be Twenty's own
// record search; swap for a real `/rest/people` / `/rest/companies`
// lookup (proxied through the worker or called from Twenty directly) once
// this is embedded in Twenty's UI.
export async function listPeople(): Promise<EntityRef[]> {
  const { data } = await fetchDailyDigest();
  if (data === fixtureDigest) return fixturePeopleRefs;
  return data.ranked_by_buying_intent.map((p) => ({
    id: p.person_id,
    name: p.name,
    companyName: p.company_name ?? undefined,
  }));
}

export async function listCompanies(): Promise<EntityRef[]> {
  const { data } = await fetchDailyDigest();
  if (data === fixtureDigest) return fixtureCompanyRefs;
  const seen = new Map<string, EntityRef>();
  for (const p of data.ranked_by_buying_intent) {
    if (p.company_name && !seen.has(p.company_name)) {
      seen.set(p.company_name, { id: p.company_name, name: p.company_name });
    }
  }
  return [...seen.values()];
}
