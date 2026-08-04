import { useEffect, useState } from 'react';

import { defineFrontComponent } from 'twenty-sdk/define';
import { useRecordId } from 'twenty-sdk/front-component';
import { enqueueSnackbar } from 'twenty-sdk/front-component';

import { CONVERSATION_PANEL_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER } from 'src/constants/universal-identifiers';
import { callAppRoute, AppRouteError } from 'src/front-components/lib/call-app-route';

/**
 * Embeds the standalone frontend's "Conversation Panel" as a native
 * Person-record-page tab: every ConversationSignal for this person, newest
 * first (Conversation Intelligence's output -- see worker/README.md), each
 * with a "Copy suggested reply" button. This folds in what the status doc
 * called the "Suggested Message button" rather than shipping it as a
 * separate component -- it only ever makes sense in the context of a
 * specific signal's `recommendedReplyDraft`, so it lives right next to it.
 *
 * Read-only + copy-to-clipboard only: this never sends anything on the
 * person's behalf, the same "draft for a human to review" boundary
 * `conversation/analyzer.py` and the Recommendation Engine both draw.
 */

type ConversationSignal = {
  id: string;
  status: string;
  interestLevel?: string | null;
  urgency?: string | null;
  sentiment?: string | null;
  objections?: string[] | null;
  nextAction?: string | null;
  replyDraft?: string | null;
  createdAt: string;
};

const ConversationPanel = () => {
  const personId = useRecordId();
  const [signals, setSignals] = useState<ConversationSignal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!personId) {
      return;
    }
    setLoading(true);
    setError(null);
    callAppRoute<ConversationSignal[]>('GET', `/worker-read/person-conversation-signals/${personId}`)
      .then(setSignals)
      .catch((err) => setError(err instanceof AppRouteError ? err.message : 'Failed to load conversation history.'))
      .finally(() => setLoading(false));
  }, [personId]);

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      await enqueueSnackbar({ message: 'Suggested reply copied to clipboard', variant: 'success' });
    } catch {
      await enqueueSnackbar({ message: 'Could not copy to clipboard', variant: 'error' });
    }
  };

  if (loading) {
    return <div style={{ padding: '16px', fontFamily: 'sans-serif', fontSize: '13px' }}>Loading conversation history…</div>;
  }

  return (
    <div style={{ padding: '16px', fontFamily: 'sans-serif', fontSize: '13px' }}>
      {error && <div style={STYLES.error}>{error}</div>}
      {signals.length === 0 ? (
        <p style={STYLES.muted}>No analyzed replies yet.</p>
      ) : (
        signals.map((signal) => (
          <div key={signal.id} style={STYLES.card}>
            <div style={STYLES.cardHeader}>
              <span>{new Date(signal.createdAt).toLocaleString()}</span>
              <span style={STYLES.badge}>{signal.interestLevel ?? 'NONE'}</span>
            </div>
            <p>
              Urgency: {signal.urgency ?? '—'} · Sentiment: {signal.sentiment ?? '—'}
            </p>
            {signal.objections && signal.objections.length > 0 && (
              <p style={STYLES.muted}>Objections: {signal.objections.join(', ')}</p>
            )}
            <p>Next action: {signal.nextAction ?? 'NO_ACTION'}</p>
            {signal.replyDraft && (
              <div style={STYLES.draftBox}>
                <p style={STYLES.muted}>Suggested reply:</p>
                <p>{signal.replyDraft}</p>
                <button onClick={() => handleCopy(signal.replyDraft as string)} style={STYLES.button}>
                  Copy suggested reply
                </button>
              </div>
            )}
          </div>
        ))
      )}
    </div>
  );
};

const STYLES: Record<string, React.CSSProperties> = {
  muted: { opacity: 0.6, fontStyle: 'italic' },
  error: { color: '#c0392b', marginBottom: '12px' },
  card: { border: '1px solid #eee', borderRadius: '8px', padding: '12px', marginBottom: '12px' },
  cardHeader: { display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '12px', opacity: 0.7 },
  badge: { background: '#eee', borderRadius: '999px', padding: '2px 10px', fontSize: '11px' },
  draftBox: { background: '#fafafa', borderRadius: '6px', padding: '10px', marginTop: '8px' },
  button: {
    marginTop: '6px',
    padding: '6px 12px',
    borderRadius: '6px',
    border: '1px solid #ccc',
    background: '#fff',
    cursor: 'pointer',
  },
};

export default defineFrontComponent({
  universalIdentifier: CONVERSATION_PANEL_FRONT_COMPONENT_UNIVERSAL_IDENTIFIER,
  name: 'conversation-panel',
  description: 'ConversationSignal history for a Person, with a copy-to-clipboard suggested reply per signal.',
  component: ConversationPanel,
});
