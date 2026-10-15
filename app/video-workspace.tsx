"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { JOB_ID, type Quality, type VideoJob, type VideoSuggestion } from "@/lib/video-types";

const examples = [
  { label: "Pythagorean theorem", prompt: "Explain the Pythagorean theorem to a beginner using a 3-4-5 triangle and squares on each side. Show why a squared plus b squared equals c squared." },
  { label: "Two-phase commit", prompt: "Explain two-phase commit with one coordinator and two participants. Show a successful prepare and commit, then explain why a participant can block while waiting for the coordinator." },
  { label: "How photosynthesis works", prompt: "Give a beginner a short overview of photosynthesis. Show sunlight, water, and carbon dioxide entering a plant, and glucose and oxygen as the outputs." },
];
const stages = [
  { key: "lesson_plan", label: "Plan the lesson", description: "Choosing the scope and explanation." },
  { key: "storyboard", label: "Compose the scenes", description: "Arranging words, diagrams, and timing." },
  { key: "coding", label: "Build the animation", description: "Turning the storyboard into a Manim scene." },
  { key: "rendering", label: "Render the video", description: "Producing your MP4. This can take a few minutes." },
];

class ApiError extends Error {
  status: number;
  constructor(detail: string, status: number) { super(detail); this.status = status; }
}

async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/backend/${path}`, {
    ...options,
    cache: "no-store",
    signal: options.signal ?? AbortSignal.timeout(130_000),
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    let message = "The request could not be completed. Try again.";
    if (typeof data?.detail === "string") message = data.detail;
    else if (Array.isArray(data?.detail)) {
      message = data.detail.map((item: { msg?: string }) => item.msg || "Invalid request").join(". ");
    }
    throw new ApiError(message, response.status);
  }
  if (!data) throw new Error("The backend returned an unreadable response. Try again.");
  return data as T;
}

function message(error: unknown) {
  return error instanceof Error ? error.message : "The request could not be completed.";
}

function rememberJob(id: string) {
  const url = new URL(window.location.href);
  url.searchParams.set("job", id);
  window.history.replaceState(null, "", url);
}

export default function VideoWorkspace() {
  const [prompt, setPrompt] = useState("");
  const [quality, setQuality] = useState<Quality>("m");
  const [share, setShare] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<VideoJob | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [searching, setSearching] = useState(false);
  const [opening, setOpening] = useState(false);
  const [restoring, setRestoring] = useState(true);
  const [formError, setFormError] = useState("");
  const [pollError, setPollError] = useState("");
  const [searchNotice, setSearchNotice] = useState("");
  const [suggestions, setSuggestions] = useState<VideoSuggestion[]>([]);
  const [videoError, setVideoError] = useState(false);
  const operation = useRef(false);
  const promptRef = useRef<HTMLTextAreaElement>(null);
  const optionsRef = useRef<HTMLDetailsElement>(null);
  const active = Boolean(jobId && (!job || job.status === "queued" || job.status === "running"));
  const busy = restoring || submitting || searching || opening || active;
  const validPrompt = prompt.trim().length >= 3 && prompt.length <= 2000;
  const phase = job?.status === "succeeded" ? stages.length : stages.findIndex((s) => s.key === job?.generation_stage);
  const videoUrl = job?.status === "succeeded" ? `/api/backend/videos/${job.job_id}.mp4` : null;

  useEffect(() => {
    const textarea = promptRef.current;
    if (!textarea) return;
    function resize() {
      if (!textarea) return;
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(Math.max(textarea.scrollHeight, 86), 260)}px`;
    }
    resize();
    let width = textarea.clientWidth;
    const observer = new ResizeObserver(() => {
      if (textarea.clientWidth === width) return;
      width = textarea.clientWidth;
      resize();
    });
    observer.observe(textarea);
    return () => observer.disconnect();
  }, [prompt]);

  useEffect(() => {
    function closeOutside(event: PointerEvent) {
      if (event.target instanceof Node && !optionsRef.current?.contains(event.target) && optionsRef.current) optionsRef.current.open = false;
    }
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    const id = new URL(window.location.href).searchParams.get("job");
    if (!id || !JOB_ID.test(id)) {
      Promise.resolve().then(() => { if (!controller.signal.aborted) setRestoring(false); });
      return () => controller.abort();
    }
    api<VideoJob>(`jobs/${id}`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]) })
      .then((saved) => {
        if (controller.signal.aborted) return;
        setJob(saved); setJobId(id); setPrompt(saved.prompt);
        if (["l", "m", "h"].includes(saved.quality)) setQuality(saved.quality as Quality);
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setJobId(id);
          setPollError(`Could not load the saved job. ${message(error)}`);
        }
      })
      .finally(() => { if (!controller.signal.aborted) setRestoring(false); });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!jobId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let failures = 0;
    async function poll() {
      try {
        const next = await api<VideoJob>(`jobs/${jobId}`, {
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]),
        });
        if (controller.signal.aborted) return;
        setJob(next); setPollError(""); failures = 0;
        if (next.status === "succeeded" || next.status === "failed") return;
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404) {
          setJobId(null); setJob(null);
          setPollError("This saved job was not found. You can generate a new video.");
          const url = new URL(window.location.href);
          url.searchParams.delete("job");
          window.history.replaceState(null, "", url);
          return;
        }
        failures++;
        setPollError(`${message(error)} Checking again automatically. Your job may still be running.`);
      }
      timer = setTimeout(poll, Math.min(2000 * (failures + 1), 15_000));
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [jobId]);

  async function generate(event: FormEvent) {
    event.preventDefault();
    if (!validPrompt || busy || operation.current) return;
    operation.current = true;
    setSubmitting(true); setFormError("");
    try {
      const created = await api<{ job_id: string }>("generate", {
        method: "POST", body: JSON.stringify({ prompt: prompt.trim(), quality, share_for_reuse: share }),
      });
      if (!JOB_ID.test(created.job_id)) throw new Error("The backend did not return a valid job ID.");
      setJob(null); setPollError(""); setVideoError(false);
      setJobId(created.job_id); rememberJob(created.job_id);
      setSuggestions([]); setSearchNotice("");
    } catch (error) {
      const uncertain = !(error instanceof ApiError) || error.status >= 500;
      setFormError(`${message(error)}${uncertain ? " If the connection was interrupted after submission, the backend may already have accepted this request." : ""}`);
    } finally {
      setSubmitting(false); operation.current = false;
    }
  }

  async function findSuggestions() {
    if (!validPrompt || busy || operation.current) return;
    operation.current = true;
    setSearching(true); setSearchNotice(""); setSuggestions([]);
    try {
      const result = await api<{ suggestions: VideoSuggestion[] }>("suggestions", {
        method: "POST", body: JSON.stringify({ prompt: prompt.trim(), quality }),
      });
      setSuggestions(result.suggestions);
      if (!result.suggestions.length) setSearchNotice("No similar videos found. You can generate a new one.");
    } catch (error) {
      setSearchNotice(`${message(error)} You can still generate a new video without searching.`);
    } finally { setSearching(false); operation.current = false; }
  }

  async function openSuggestion(id: string) {
    if (busy || operation.current || !JOB_ID.test(id)) return;
    operation.current = true; setOpening(true); setFormError("");
    try {
      const selected = await api<VideoJob>(`jobs/${id}`);
      setJob(selected); setJobId(id); setPollError(""); setVideoError(false); rememberJob(id);
    } catch (error) { setFormError(message(error)); }
    finally { setOpening(false); operation.current = false; }
  }

  function fillExample(value: string) {
    setPrompt(value); setSuggestions([]); setSearchNotice("");
    promptRef.current?.focus();
  }

  return (
    <div className={`workbench ${jobId || submitting || pollError ? "workspace-started" : "workspace-empty"}`}>
      <a className="skip-link" href="#prompt">Skip to your request</a>
      <main className="studio-main">
        <div className="intro">
          <h1>What would you like to explain?</h1>
        </div>

        <section className="request-panel" aria-label="Create a video">
          <form onSubmit={generate} id="request">
            <label className="sr-only" htmlFor="prompt">Your lesson request</label>
            <textarea
              ref={promptRef}
              id="prompt"
              value={prompt}
              onChange={(event) => { setPrompt(event.target.value); setSuggestions([]); setSearchNotice(""); }}
              disabled={busy}
              minLength={3}
              maxLength={2000}
              required
              placeholder="Describe an idea to animate…"
              aria-describedby={prompt.length > 1800 ? "prompt-count" : undefined}
            />
            {prompt.length > 1800 && <span className="prompt-count" id="prompt-count">{prompt.length} / 2,000</span>}
            <div className="composer-toolbar">
          <details ref={optionsRef} className="options-details" onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.currentTarget.open = false;
              event.currentTarget.querySelector("summary")?.focus();
            }
          }}>
            <summary>Options{share && <span className="sharing-indicator">Sharing on</span>}</summary>
            <div className="options-content">
              <fieldset disabled={busy}>
                <legend>Video quality</legend>
                <div className="quality-options">
                  {([{ value: "l", label: "Preview", detail: "480p" }, { value: "m", label: "Standard", detail: "720p" }, { value: "h", label: "High", detail: "1080p" }] as const).map((option) => (
                    <label key={option.value} className={quality === option.value ? "selected" : ""}>
                      <input type="radio" name="quality" value={option.value} checked={quality === option.value} onChange={() => { setQuality(option.value); setSuggestions([]); setSearchNotice(""); }} />
                      <span>{option.label}<small>{option.detail}</small></span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <label className="share-control">
                <input type="checkbox" checked={share} onChange={(event) => setShare(event.target.checked)} disabled={busy} />
                <span>Let others reuse this video<small>Shares the video and your original request. Requires reuse to be enabled.</small></span>
              </label>
              <button className="text-button" type="button" onClick={findSuggestions} disabled={!validPrompt || busy}>
                {searching ? "Searching…" : "Find an existing video"}
              </button>
              {searchNotice && <p className="search-notice" role="status">{searchNotice}</p>}
              {suggestions.length > 0 && <div className="suggestions" aria-label="Similar videos">
                {suggestions.map((suggestion) => (
                  <div className="suggestion" key={suggestion.job_id}>
                    <p>{suggestion.prompt}</p>
                    <button className="text-button" type="button" onClick={() => openSuggestion(suggestion.job_id)} disabled={busy}>Preview this video</button>
                  </div>
                ))}
              </div>}
            </div>
          </details>
              <div className="composer-submit">
                {(submitting || active) && <span className="composer-state">{submitting ? "Submitting…" : "Creating…"}</span>}
                <button className="send-button" type="submit" disabled={!validPrompt || busy} aria-label={submitting ? "Submitting request" : active ? "Creating video" : "Generate video"} title="Generate video">
                  <span aria-hidden="true">↑</span>
                </button>
              </div>
            </div>
          </form>
          {formError && <p className="error-message" role="alert">{formError}</p>}
        </section>

        <div className="secondary-controls">
          {!prompt && <div className="examples" aria-label="Example requests">
            {examples.slice(0, 2).map((example) => <button key={example.label} type="button" onClick={() => fillExample(example.prompt)} disabled={busy}>{example.label}</button>)}
          </div>}
        </div>

        {pollError && <p className="error-message" role="alert">{pollError}</p>}
        {(active || submitting) && <section className="generation-progress" role="status" aria-live="polite" aria-label="Video progress">
          <span className="render-spinner" aria-hidden="true" />
          <div>
            <h2>{submitting ? "Sending your request" : job?.status === "queued" ? "Your video is queued" : phase >= 0 ? stages[phase]?.label : "Creating your video"}</h2>
            <p>This may take a few minutes.</p>
          </div>
        </section>}

        {job?.status === "failed" && <section className="failure-panel" role="alert">
          <h2>We couldn&apos;t create this video.</h2>
          <p>Edit your request and try again.</p>
          <details><summary>Error details</summary><pre>{job.error || "No error details available."}</pre></details>
        </section>}

        {videoUrl && <section className="result-panel" aria-labelledby="result-title">
          <div className="result-heading">
            <h2 id="result-title">{job?.storyboard?.title || "Your video"}</h2>
            <a className="download-button" href={videoUrl} download={`forma-${job?.job_id}.mp4`}>Download MP4</a>
          </div>
          <div className="preview-frame">
            <video key={videoUrl} controls playsInline preload="metadata" src={videoUrl} onError={() => setVideoError(true)} aria-label="Generated lesson video" />
          </div>
          {videoError && <p className="error-message" role="alert">The video couldn&apos;t load. Reload the page or try downloading it.</p>}
          <details className="lesson-details">
            <summary>View lesson details</summary>
            <div className="lesson-content">
              <h3>Original request</h3><p>{job?.prompt}</p>
              {job?.lesson_plan && <>
                <h3>Lesson plan</h3>
                <p>{job.lesson_plan.objective}</p>
                <ol>{job.lesson_plan.steps.map((step, index) => <li key={index}>{step.explanation}</li>)}</ol>
                <p className="takeaway">{job.lesson_plan.takeaway}</p>
              </>}
              {job?.storyboard && <>
                <h3>Scene sequence</h3>
                <ol>{job.storyboard.beats.map((beat, index) => <li key={index}>{beat.caption}</li>)}</ol>
              </>}
              {job?.reuse_error && <p className="search-notice">Your video is ready, but couldn&apos;t be added to video search.</p>}
              <p className="job-reference">Job {jobId}</p>
            </div>
          </details>
        </section>}
      </main>
    </div>
  );
}
