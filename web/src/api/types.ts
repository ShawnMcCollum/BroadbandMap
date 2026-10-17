export type StateSummary = { code: string; name: string; abbreviation: string };
export type ReleaseSummary = {
  filing_period: string;
  as_of: string;
  processed_on: string;
  states: StateSummary[];
};
export type ReleasePage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: ReleaseSummary[];
};
export type Flag = 'wired' | 'any' | 'terrestrial';
export type Selection = {
  as_of: string;
  processed_on: string;
  state: '39';
  flag: Flag;
  county: string | null;
};
export type SummaryCoverage =
  'stored_rollups_only' | 'observed' | 'no_observations' | 'outside_release_coverage';
export type SummaryLevel =
  'county' | 'tract' | 'block_group' | 'block' | 'h3_res8' | 'place' | 'county_subdivision';
export type RollupRow = {
  code: string;
  locations: number;
  served: number;
  not_served: number;
  wired_100_20: number;
  any_100_20: number;
  terrestrial_100_20: number;
};
export type RollupPage = {
  boundary_vintage: number | null;
  count: number;
  next: string | null;
  previous: string | null;
  release: ReleaseSummary;
  results: RollupRow[];
  selection: { level: SummaryLevel; state: string | null; code: string | null; flag: Flag };
  summary_coverage: SummaryCoverage;
  threshold: { download_mbps: number; upload_mbps: number };
};
export type ProblemField = { pointer: string; code: string; message: string };
export type Problem = {
  type: string;
  title: string;
  status: number;
  detail: string;
  code: string;
  request_id: string;
  errors?: ProblemField[];
};
export type ApiFailureKind =
  'problem' | 'http' | 'unexpected' | 'network' | 'timeout' | 'cancelled';
export class ApiFailure extends Error {
  constructor(
    public kind: ApiFailureKind,
    message: string,
    public status?: number,
    public problem?: Problem,
    public requestId?: string,
  ) {
    super(message);
    this.name = 'ApiFailure';
  }
}
