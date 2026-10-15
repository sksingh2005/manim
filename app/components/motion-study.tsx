"use client";

import { useEffect, useRef, useState } from "react";

export default function MotionStudy() {
  const [playing, setPlaying] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(false);
  const dot = useRef<SVGCircleElement>(null);
  const radius = useRef<SVGLineElement>(null);
  const projection = useRef<SVGLineElement>(null);
  const wave = useRef<SVGPathElement>(null);
  const wavePoint = useRef<SVGCircleElement>(null);
  const phase = useRef(0.8);
  const elapsed = useRef(0);
  const scrubber = useRef<HTMLInputElement>(null);
  const timeLabel = useRef<HTMLOutputElement>(null);
  const [seek, setSeek] = useState(0);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    let frame = 0;
    let previous = 0;
    function draw(time: number) {
      if (previous && playing && !reducedMotion) {
        elapsed.current += Math.min(time - previous, 80);
        phase.current = 0.8 + elapsed.current / 12000 * Math.PI * 2;
      }
      previous = time;
      const angle = phase.current;
      const x = 132 + 68 * Math.cos(angle);
      const y = 153 - 68 * Math.sin(angle);
      dot.current?.setAttribute("cx", x.toFixed(2));
      dot.current?.setAttribute("cy", y.toFixed(2));
      radius.current?.setAttribute("x2", x.toFixed(2));
      radius.current?.setAttribute("y2", y.toFixed(2));
      projection.current?.setAttribute("x1", x.toFixed(2));
      projection.current?.setAttribute("y1", y.toFixed(2));
      projection.current?.setAttribute("y2", y.toFixed(2));
      wavePoint.current?.setAttribute("cy", y.toFixed(2));
      const points = Array.from({ length: 101 }, (_, i) => {
        const px = 246 + i * 2.58;
        const py = 153 - 68 * Math.sin(angle - i / 100 * Math.PI * 2);
        return `${i === 0 ? "M" : "L"}${px.toFixed(2)},${py.toFixed(2)}`;
      }).join(" ");
      wave.current?.setAttribute("d", points);
      const seconds = (elapsed.current % 12000) / 1000;
      if (scrubber.current) scrubber.current.value = seconds.toFixed(2);
      if (timeLabel.current) timeLabel.current.textContent = `0:${Math.floor(seconds).toString().padStart(2, "0")} / 0:12`;
      if (playing && !reducedMotion) frame = requestAnimationFrame(draw);
    }
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [playing, reducedMotion, seek]);

  return (
    <div className="motion-study">
      <div className="study-topline"><span>A circle becomes a wave.</span><span className="study-label">Interactive example</span></div>
      <svg viewBox="0 0 560 310" role="img" aria-label="An animated diagram showing how circular motion produces a sine wave">
        <defs>
          <pattern id="study-grid" width="28" height="28" patternUnits="userSpaceOnUse"><path d="M28 0H0V28" fill="none" stroke="#ffffff" strokeOpacity=".035" /></pattern>
          <linearGradient id="wave-color" x1="246" y1="0" x2="510" y2="0" gradientUnits="userSpaceOnUse">
            <stop stopColor="#c6bef5" /><stop offset="1" stopColor="#8075b3" />
          </linearGradient>
        </defs>
        <rect width="560" height="310" fill="url(#study-grid)" />
        <g className="study-guides" fill="none" strokeWidth="1">
          <path d="M42 153H521M132 54V251M246 62V242" />
          <circle cx="132" cy="153" r="68" />
          <path d="M246 85H510M246 221H510" strokeDasharray="2 7" />
        </g>
        <circle cx="132" cy="153" r="3" fill="#74717f" />
        <line ref={radius} x1="132" y1="153" x2="179.38" y2="104.22" stroke="#a29abf" strokeWidth="1.5" />
        <line ref={projection} x1="179.38" y1="104.22" x2="246" y2="104.22" stroke="#726888" strokeWidth="1" strokeDasharray="3 5" />
        <circle ref={dot} cx="179.38" cy="104.22" r="5" fill="#d4ccff" />
        <path ref={wave} d="M246 104 Q305 48 375 180 T504 104" stroke="url(#wave-color)" strokeWidth="2.5" fill="none" strokeLinecap="round" />
        <circle ref={wavePoint} cx="246" cy="104.22" r="4" fill="#d4ccff" />
        <g className="study-annotations" textAnchor="middle">
          <text x="132" y="278">Circular motion</text><text x="378" y="278">Sine wave</text>
        </g>
      </svg>
      <div className="study-bottomline">
        <button type="button" onClick={() => setPlaying(!playing)} disabled={reducedMotion} aria-label={reducedMotion ? "Animation disabled for reduced motion" : playing ? "Pause animation" : "Play animation"}>
          {playing && !reducedMotion ? "Pause" : "Play"}
        </button>
        <input ref={scrubber} type="range" min="0" max="12" step="0.01" defaultValue="0" aria-label="Explore the animation" onChange={(event) => { elapsed.current = Number(event.target.value) * 1000; phase.current = 0.8 + elapsed.current / 12000 * Math.PI * 2; setPlaying(false); setSeek((value) => value + 1); }} />
        <output ref={timeLabel} aria-live="off">0:00 / 0:12</output>
      </div>
    </div>
  );
}
