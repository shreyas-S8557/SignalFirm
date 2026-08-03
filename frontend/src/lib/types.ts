// Mirrors worker/scrapegraph_worker/recommendations/models.py and
// conversation/models.py field-for-field. Those Pydantic models have no
// alias_generator, so FastAPI serializes them snake_case as declared --
// these types intentionally match that, not Twenty's own camelCase (that
// distinction matters at the two /people and /companies endpoints below,
// which *do* pass Twenty's raw camelCase through untouched).

export type Bucket = "CONTACT_TODAY" | "MONITOR" | "IGNORE";
export type Temperature = "HOT" | "WARM" | "COLD";
export type InterestLevel = "HIGH" | "MEDIUM" | "LOW" | "NONE";
export type Urgency = "HIGH" | "MEDIUM" | "LOW";
export type Sentiment = "POSITIVE" | "NEUTRAL" | "NEGATIVE" | "MIXED";
export type NextAction =
  | "SEND_REPLY"
  | "SCHEDULE_FOLLOW_UP"
  | "ESCALATE_TO_HUMAN"
  | "MARK_WON"
  | "MARK_LOST"
  | "NO_ACTION";

export interface PersonRecommendation {
  person_id: string;
  name: string;
  email?: string | null;
  company_name?: string | null;
  interest_level: InterestLevel | string;
  urgency: Urgency | string;
  sentiment?: Sentiment | string | null;
  latest_next_action?: NextAction | string | null;
  latest_objections?: string | null;
  latest_confidence?: number | null;
  last_signal_at?: string | null;
  days_since_signal?: number | null;
  icp_score?: number | null;
  icp_priority?: string | null;
  buying_intent_score: number;
  temperature: Temperature;
  bucket: Bucket;
  reason: string;
  best_message: string;
}

export interface DailyDigest {
  generated_at: string;
  considered_count: number;
  contact_today: PersonRecommendation[];
  ignore: PersonRecommendation[];
  hot: PersonRecommendation[];
  cold: PersonRecommendation[];
  ranked_by_buying_intent: PersonRecommendation[];
  top_pick?: PersonRecommendation | null;
}

// -- Twenty's own camelCase field names, passed through untouched by the
// two list endpoints (see api.py "Phase 9" section docstring). --

export interface ConversationSignal {
  id: string;
  status: "PENDING" | "COMPLETED" | "FAILED";
  interestLevel: InterestLevel;
  urgency: Urgency;
  sentiment: Sentiment;
  objections?: string | null;
  recommendedNextAction: NextAction;
  recommendedReplyDraft?: string | null;
  recommendedFollowUpAt?: string | null;
  confidence: number;
  sourceMessageId?: string | null;
  rawExcerpt?: string | null;
  modelUsed?: string | null;
  errorMessage?: string | null;
  createdAt: string;
}

export interface ResearchJob {
  id: string;
  status: "IMPORTED" | "SKIPPED" | "FAILED";
  source?: string | null;
  sourceRunId?: string | null;
  createdAt: string;
}

export interface CompanyInsights {
  company_id: string;
  company_name?: string | null;
  latest_icp_score?: number | null;
  latest_icp_priority?: "HIGH" | "MEDIUM" | "LOW" | null;
  last_enriched_at?: string | null;
  icp_reasoning?: string | null;
  icp_rubric_version?: string | null;
  research_job_count: number;
  last_research_at?: string | null;
  person_count: number;
  people_by_interest_level: Record<string, number>;
  most_recent_signal_at?: string | null;
  generated_at: string;
}

export interface EntityRef {
  id: string;
  name: string;
  companyName?: string;
}
