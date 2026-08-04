import { useEffect, useState } from 'react';

import { defineFrontComponent } from 'twenty-sdk/define';
import { useRecordId } from 'twenty-sdk/front-component';

import { AI_INSIGHTS_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { callAppRoute, AppRouteError } from 'src/front-components/lib/call-app-route';

/**
 * Embeds the standalone frontend's "AI Insights Panel" (frontend/README.md)
 * as a native Company-record-page tab. Reads worker/scrapegraph_worker/api.py's
 * `GET /companies/{id}/insights` (Phase 9) and `GET /companies/{id}/workflow`
 * (Phase 7) through worker-read-proxy.ts, and offers an "Enrich now" button
 * that POSTs through worker-action-proxy.ts to Phase 4's
 * `POST /companies/{id}/enrich`.
 *
 * Honest about what it doesn't have yet: ICP score fields render as
 * "Not scored yet" rather than a fabricated number (mirrors
 * CompanyInsights's own "report the scaffold as it is" rule), and the
 * workflow stage's blockedReason is shown verbatim when the pipeline is
 * blocked on Research Automation / ICP Scoring / AI Outbound Messaging
 * rather than being hidden.
 */

type CompanyInsights = {
  company_name?: string | null;
  latest_icp_score?: number | null;
  latest_icp_priority?: string | null;
  enrichment_status?: string | null;
  enrichment_summary?: string | null;
  enrichment_tech_stack?: string[];
  enrichment_ai_maturity?: string | null;
  last_enrichment_at?: string | null;
  research_job_count?: number;
  person_count?: number;
  people_by_interest_level?: Record<string, number>;
};

type WorkflowState = {
  stage: string;
  blocked: boolean;
  blocked_reason?: string | null;
  next_action?: string | null;
};

const AiInsightsPanel = () => {
  const companyId = useRecordId();

  const [insights, setInsights] = useState<CompanyInsights | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [enriching, setEnriching] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [insightsData, workflowData] = await Promise.all([
        callAppRoute<CompanyInsights>('GET', `/worker-read/company-insights/${companyId}`),
        callAppRoute<WorkflowState>('GET', `/worker-read/company-workflow/${companyId}`),
      ]);
      setInsights(insightsData);
      setWorkflow(workflowData);
    } catch (err) {
      setError(err instanceof AppRouteError ? err.message : 'Failed to load AI insights.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (companyId) {
      load();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companyId]);

  const handleEnrichNow = async () => {
    setEnriching(true);
    setError(null);
    try {
      await callAppRoute('POST', `/worker-action/enrich/${companyId}`);
      await load();
    } catch (err) {
      setError(err instanceof AppRouteError ? err.message : 'Enrichment failed.');
    } finally {
      setEnriching(false);
    }
  };

  if (loading) {
    return <div style={STYLES.container}>Loading AI insights…</div>;
  }

  return (
    <div style={STYLES.container}>
      {error && <div style={STYLES.error}>{error}</div>}

      <Section title="ICP Score">
        {insights?.latest_icp_score != null ? (
          <p>
            {insights.latest_icp_score} / 100 — <strong>{insights.latest_icp_priority}</strong>
          </p>
        ) : (
          <p style={STYLES.muted}>Not scored yet — run ICP Scoring (POST /companies/{'{id}'}/icp-score or Workflow Automation's advance()) once the company has been enriched and researched.</p>
        )}
      </Section>

      <Section title="Company Summary">
        {insights?.enrichment_summary ? (
          <p>{insights.enrichment_summary}</p>
        ) : (
          <p style={STYLES.muted}>Not enriched yet.</p>
        )}
      </Section>

      <Section title="Tech Stack">
        {insights?.enrichment_tech_stack && insights.enrichment_tech_stack.length > 0 ? (
          <div style={STYLES.chipRow}>
            {insights.enrichment_tech_stack.map((tech) => (
              <span key={tech} style={STYLES.chip}>
                {tech}
              </span>
            ))}
          </div>
        ) : (
          <p style={STYLES.muted}>No technologies detected yet.</p>
        )}
      </Section>

      <Section title="AI Maturity">
        <p>{insights?.enrichment_ai_maturity ?? 'UNKNOWN'}</p>
      </Section>

      <Section title="Pipeline Status">
        {workflow ? (
          <>
            <p>
              Stage: <strong>{workflow.stage}</strong>
            </p>
            {workflow.blocked && workflow.blocked_reason && <p style={STYLES.muted}>{workflow.blocked_reason}</p>}
            {workflow.next_action && <p style={STYLES.muted}>Next: {workflow.next_action}</p>}
          </>
        ) : (
          <p style={STYLES.muted}>Unknown.</p>
        )}
      </Section>

      <Section title="Engagement">
        <p>
          {insights?.person_count ?? 0} people synced · {insights?.research_job_count ?? 0} research jobs
        </p>
      </Section>

      <button onClick={handleEnrichNow} disabled={enriching} style={STYLES.button}>
        {enriching ? 'Enriching…' : 'Enrich now'}
      </button>
    </div>
  );
};

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <div style={STYLES.section}>
    <div style={STYLES.sectionTitle}>{title}</div>
    {children}
  </div>
);

const STYLES: Record<string, React.CSSProperties> = {
  container: { padding: '16px', fontFamily: 'sans-serif', fontSize: '13px' },
  section: { marginBottom: '16px' },
  sectionTitle: { fontWeight: 600, marginBottom: '4px', fontSize: '12px', textTransform: 'uppercase', opacity: 0.6 },
  muted: { opacity: 0.6, fontStyle: 'italic' },
  error: { color: '#c0392b', marginBottom: '12px' },
  chipRow: { display: 'flex', flexWrap: 'wrap', gap: '6px' },
  chip: { background: '#eee', borderRadius: '999px', padding: '2px 10px', fontSize: '12px' },
  button: {
    padding: '8px 16px',
    borderRadius: '6px',
    border: 'none',
    background: '#333',
    color: '#fff',
    cursor: 'pointer',
  },
};

export default defineFrontComponent({
  universalIdentifier: AI_INSIGHTS_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
  name: 'ai-insights-panel',
  description: "AI Insights panel: ICP score, enrichment summary, tech stack, AI maturity, and pipeline status for a Company.",
  component: AiInsightsPanel,
});
