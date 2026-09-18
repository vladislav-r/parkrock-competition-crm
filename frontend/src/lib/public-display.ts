export type PublicDisplaySettings = {
  tv_interval_seconds: number;
  tv_stage: "qualification" | "final";
  tv_teams: boolean;
  tv_rows_per_column: number;
  tv_max_columns: number;
  tv_controls_hide_seconds: number;
  tv_highlight_top: number;
  sponsors_enabled: boolean;
  tv_sponsors_enabled: boolean;
  sponsor_featured_seconds: number;
  sponsor_regular_seconds: number;
  tv_sponsor_featured_seconds: number;
  tv_sponsor_regular_seconds: number;
};

export const PUBLIC_DISPLAY_DEFAULTS: PublicDisplaySettings = {
  tv_interval_seconds: 15,
  tv_stage: "qualification",
  tv_teams: false,
  tv_rows_per_column: 30,
  tv_max_columns: 2,
  tv_controls_hide_seconds: 3,
  tv_highlight_top: 10,
  sponsors_enabled: true,
  tv_sponsors_enabled: true,
  sponsor_featured_seconds: 44,
  sponsor_regular_seconds: 56,
  tv_sponsor_featured_seconds: 44,
  tv_sponsor_regular_seconds: 56,
};
