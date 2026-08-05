import { useEffect, useState } from 'react';

import { defineFrontComponent } from 'twenty-sdk/define';
import { useSelectedRecordIds } from 'twenty-sdk/front-component';

import { RESEARCH_TAB_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { callAppRoute, AppRouteError } from 'src/front-components/lib/call-app-route';

/**
 * Embeds the standalone frontend's "Research Tab" as a native Company tab:
 * a merged timeline of ResearchJob (sync attempts) and EnrichmentJob
 * (Phase 4 crawl attempts) records, newest first, plus a manual
 * "Advance workflow" button (Phase 7's `POST .../workflow/advance`) for
 * cases where a human wants to nudge the pipeline rather than wait for
 * the scheduler.
 */

type ResearchJob = {
  id: string;
  status: string;
  source?: string | null;
  createdAt: string;
  researchSummary?: string | null;
  painPoints?: string | null;
  salesAngles?: string | null;
  researchBuyingSignals?: string | null;
  researchConfidence?: number | null;
  errorMessage?: string | null;
};

const RESEARCH_STATUSES = new Set(['RESEARCHED', 'RESEARCH_FAILED']);

type EnrichmentJob = {
  id: string;
  status: string;
  provider?: string | null;
  confidence?: number | null;
  errorMessage?: string | null;
  createdAt: string;
};

type TimelineEntry = {
  id: string;
  kind: 'Research' | 'Enrichment';
  status: string;
  detail: string;
  createdAt: string;
};

const ResearchTab = () => {
  // useRecordId() is deprecated in SDK 2.27 -- see ai-insights-panel's comment.
  const selectedRecordIds = useSelectedRecordIds();
  const companyId = selectedRecordIds.length === 1 ? selectedRecordIds[0] : null;
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [latestResearch, setLatestResearch] = useState<ResearchJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [advancing, setAdvancing] = useState(false);
  const [advanceResult, setAdvanceResult] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [researchJobs, enrichmentJobs] = await Promise.all([
        callAppRoute<ResearchJob[]>('GET', `/worker-read/company-research-jobs/${companyId}`),
        callAppRoute<EnrichmentJob[]>('GET', `/worker-read/company-enrichment-jobs/${companyId}`),
      ]);

      const merged: TimelineEntry[] = [
        ...researchJobs.map((job) => ({
          id: job.id,
          kind: 'Research' as const,
          status: job.status,
          detail: job.source ?? '',
          createdAt: job.createdAt,
        })),
        ...enrichmentJobs.map((job) => ({
          id: job.id,
          kind: 'Enrichment' as const,
          status: job.status,
          detail: job.errorMessage ?? `confidence=${job.confidence ?? 0}`,
          createdAt: job.createdAt,
        })),
      ].sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1));

      setEntries(merged);
      // Records come back newest-first, so the first research-status row is
      // the current brief. Import-status rows (IMPORTED/SKIPPED/FAILED) live
      // in the same object and are deliberately not treated as research.
      setLatestResearch(researchJobs.find((job) => RESEARCH_STATUSES.has(job.status)) ?? null);
    } catch (err) {
      setError(err instanceof AppRouteError ? err.message : 'Failed to load research history.');
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

  const handleAdvance = async () => {
    setAdvancing(true);
    setAdvanceResult(null);
    try {
      const result = await callAppRoute<{ action_taken: string; detail?: string | null }>(
        'POST',
        `/worker-action/workflow-advance/${companyId}`,
      );
      setAdvanceResult(`${result.action_taken}${result.detail ? ` — ${result.detail}` : ''}`);
      await load();
    } catch (err) {
      setAdvanceResult(err instanceof AppRouteError ? err.message : 'Advance failed.');
    } finally {
      setAdvancing(false);
    }
  };

  return (
    <div style={{ padding: '16px', fontFamily: 'sans-serif', fontSize: '13px' }}>
      <button onClick={handleAdvance} disabled={advancing} style={STYLES.button}>
        {advancing ? 'Advancing…' : 'Advance workflow'}
      </button>
      {advanceResult && <p style={STYLES.muted}>{advanceResult}</p>}

      {error && <div style={STYLES.error}>{error}</div>}

      {latestResearch && latestResearch.status === 'RESEARCH_FAILED' && (
        <div style={STYLES.brief}>
          <div style={STYLES.briefTitle}>Latest research run failed</div>
          <p style={STYLES.muted}>{latestResearch.errorMessage ?? 'No reason recorded.'}</p>
        </div>
      )}

      {latestResearch && latestResearch.status === 'RESEARCHED' && (
        <div style={STYLES.brief}>
          <div style={STYLES.briefTitle}>
            Research brief
            {latestResearch.researchConfidence != null && (
              <span style={STYLES.muted}> · confidence {latestResearch.researchConfidence.toFixed(2)}</span>
            )}
          </div>

          {latestResearch.researchSummary && <p>{latestResearch.researchSummary}</p>}

          {/* Pain points and sales angles are inferences, not findings --
              the banner is not decorative, it's the same caveat the CRM
              field descriptions and the worker's rendered output carry. */}
          {(latestResearch.painPoints || latestResearch.salesAngles) && (
            <p style={STYLES.caveat}>
              Pain points and sales angles below are AI-generated hypotheses, not verified facts. Validate them before
              treating any as true about this company.
            </p>
          )}

          {latestResearch.painPoints && (
            <>
              <div style={STYLES.subTitle}>Pain points (hypotheses)</div>
              <pre style={STYLES.pre}>{latestResearch.painPoints}</pre>
            </>
          )}

          {latestResearch.salesAngles && (
            <>
              <div style={STYLES.subTitle}>Sales angles (hypotheses)</div>
              <pre style={STYLES.pre}>{latestResearch.salesAngles}</pre>
            </>
          )}

          {latestResearch.researchBuyingSignals && (
            <>
              <div style={STYLES.subTitle}>Buying signals (interpreted)</div>
              <pre style={STYLES.pre}>{latestResearch.researchBuyingSignals}</pre>
            </>
          )}
        </div>
      )}

      {loading ? (
        <p>Loading…</p>
      ) : entries.length === 0 ? (
        <p style={STYLES.muted}>No research or enrichment attempts yet.</p>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '12px' }}>
          <thead>
            <tr>
              <th style={STYLES.th}>When</th>
              <th style={STYLES.th}>Type</th>
              <th style={STYLES.th}>Status</th>
              <th style={STYLES.th}>Detail</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td style={STYLES.td}>{new Date(entry.createdAt).toLocaleString()}</td>
                <td style={STYLES.td}>{entry.kind}</td>
                <td style={STYLES.td}>{entry.status}</td>
                <td style={STYLES.td}>{entry.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

const STYLES: Record<string, React.CSSProperties> = {
  muted: { opacity: 0.6, fontStyle: 'italic', fontSize: '12px' },
  error: { color: '#c0392b', marginBottom: '12px' },
  brief: { border: '1px solid #eee', borderRadius: '8px', padding: '12px', margin: '12px 0' },
  briefTitle: { fontWeight: 600, marginBottom: '6px' },
  subTitle: { fontWeight: 600, fontSize: '12px', marginTop: '10px', marginBottom: '2px' },
  caveat: {
    background: '#fff8e1',
    border: '1px solid #ffe082',
    borderRadius: '6px',
    padding: '8px 10px',
    fontSize: '12px',
    margin: '10px 0',
  },
  pre: { whiteSpace: 'pre-wrap', fontFamily: 'inherit', margin: 0, fontSize: '12px' },
  th: { textAlign: 'left', borderBottom: '1px solid #ddd', padding: '6px 8px', fontSize: '11px', opacity: 0.7 },
  td: { borderBottom: '1px solid #f0f0f0', padding: '6px 8px' },
  button: {
    padding: '6px 14px',
    borderRadius: '6px',
    border: '1px solid #ccc',
    background: '#fff',
    cursor: 'pointer',
  },
};

export default defineFrontComponent({
  universalIdentifier: RESEARCH_TAB_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
  name: 'research-tab',
  description: 'Merged Research Job / Enrichment Job timeline for a Company, plus a manual workflow-advance button.',
  component: ResearchTab,
});
