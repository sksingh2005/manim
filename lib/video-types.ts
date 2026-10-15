export type Quality = "l" | "m" | "h";

export interface LessonPlan {
  audience: string;
  objective: string;
  scope: string;
  steps: { explanation: string; visual_intent: string }[];
  takeaway: string;
}

export interface Storyboard {
  title: string;
  beats: { caption: string; animation_seconds: number; hold_seconds: number }[];
}

export interface VideoJob {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  prompt: string;
  quality: string;
  generation_stage: string | null;
  lesson_plan: LessonPlan | null;
  storyboard: Storyboard | null;
  error: string | null;
  share_for_reuse: boolean;
  reuse_error: string | null;
}

export interface VideoSuggestion {
  job_id: string;
  prompt: string;
  score: number;
}

export const JOB_ID = /^[a-f0-9]{32}$/;
