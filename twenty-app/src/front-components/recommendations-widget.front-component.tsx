import { useEffect, useState } from 'react';

import { defineFrontComponent } from 'twenty-sdk/define';

import { RECOMMENDATIONS_WIDGET_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { callAppRoute, AppRouteError } from 'src/front-components/lib/call-app-route';

/**
 * Embeds the standalone frontend's "Recommendations Widget" as a native
 * dashboard page: today's Contact Today / Monitor / Ignore buckets from
 * the Recommendation Engine (`GET /recommendations/daily-digest`), via
 * worker-daily-digest-proxy.ts. Not record-scoped (no useSelectedRecordIds) --
 * this is workspace-wide, same as the digest itself.
 *
 * Read-only, same as the standalone version: this never sends anything.
 */

type PersonRecommendation = {
  person_id: string;
  name: string;
  company_name?: string | null;
  interest_level: string;
  urgency: string;
  buying_intent_score: number;
  temperature: string;
  bucket: string;
  reason: string;
  best_message: string;
};

type DailyDigest = {
  generated_at: string;
  considered_count: number;
  contact_today: PersonRecommendation[];
  monitor?: PersonRecommendation[];
  ignore: PersonRecommendation[];
  hot: PersonRecommendation[];
};

const RecommendationsWidget = () => {
  const [digest, setDigest] = useState<DailyDigest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    callAppRoute<DailyDigest>('GET', '/worker-daily-digest')
      .then(setDigest)
      .catch((err) => setError(err instanceof AppRouteError ? err.message : 'Failed to load recommendations.'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div style={{ padding: '16px', fontFamily: 'sans-serif' }}>Loading today's recommendations…</div>;
  }

  if (error) {
    return (
      <div style={{ padding: '16px', fontFamily: 'sans-serif', color: '#c0392b' }}>
        {error}
      </div>
    );
  }

  if (!digest || digest.considered_count === 0) {
    return (
      <div style={{ padding: '16px', fontFamily: 'sans-serif', opacity: 0.6, fontStyle: 'italic' }}>
        No one with an analyzed reply yet — the Recommendation Engine only considers people who've replied at least
        once (see worker/README.md).
      </div>
    );
  }

  return (
    <div style={{ padding: '16px', fontFamily: 'sans-serif', fontSize: '13px' }}>
      <p style={STYLES.muted}>
        Generated {new Date(digest.generated_at).toLocaleString()} · {digest.considered_count} people considered
      </p>

      <Bucket title="Contact Today" people={digest.contact_today} />
      <Bucket title="Hot" people={digest.hot} />
      <Bucket title="Ignore" people={digest.ignore} />
    </div>
  );
};

const Bucket = ({ title, people }: { title: string; people: PersonRecommendation[] }) => {
  if (people.length === 0) {
    return null;
  }
  return (
    <div style={{ marginBottom: '20px' }}>
      <h3 style={{ fontSize: '14px', marginBottom: '8px' }}>
        {title} ({people.length})
      </h3>
      {people.map((person) => (
        <div key={person.person_id} style={STYLES.card}>
          <div style={STYLES.cardHeader}>
            <strong>{person.name}</strong>
            <span style={STYLES.badge}>{person.temperature}</span>
          </div>
          {person.company_name && <p style={STYLES.muted}>{person.company_name}</p>}
          <p>Score: {person.buying_intent_score.toFixed(0)} — {person.reason}</p>
          <p style={STYLES.muted}>{person.best_message}</p>
        </div>
      ))}
    </div>
  );
};

const STYLES: Record<string, React.CSSProperties> = {
  muted: { opacity: 0.6, fontSize: '12px' },
  card: { border: '1px solid #eee', borderRadius: '8px', padding: '10px', marginBottom: '8px' },
  cardHeader: { display: 'flex', justifyContent: 'space-between', marginBottom: '4px' },
  badge: { background: '#eee', borderRadius: '999px', padding: '2px 10px', fontSize: '11px' },
};

export default defineFrontComponent({
  universalIdentifier: RECOMMENDATIONS_WIDGET_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
  name: 'recommendations-widget',
  description: "Today's Recommendation Engine digest (Contact Today / Hot / Ignore) as a standalone dashboard page.",
  component: RecommendationsWidget,
});
