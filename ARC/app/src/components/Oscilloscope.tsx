import { useEffect, useRef } from "react";

/**
 * Oscilloscope trace. Without a microphone module it honestly shows "НЕТ СИГНАЛА" with a flat,
 * slightly noisy baseline; while a command is processed it shows a carrier wave.
 * Stage 2 feeds real microphone levels through `levels`.
 */
export function Oscilloscope({ active, levels, label }: { active: boolean; levels?: number[]; label: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const activeRef = useRef(active);
  const levelsRef = useRef(levels);
  activeRef.current = active;
  levelsRef.current = levels;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let frame = 0;
    let raf = 0;
    const animated = () => document.documentElement.dataset.anim !== "off";

    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const styles = getComputedStyle(document.documentElement);
      const accent = styles.getPropertyValue("--accent").trim() || "#ffb000";
      const line = styles.getPropertyValue("--line").trim() || "rgba(255,176,0,.16)";
      // graticule
      ctx.strokeStyle = line;
      ctx.lineWidth = 1;
      for (let x = 0; x <= w; x += w / 10) {
        ctx.beginPath();
        ctx.moveTo(Math.round(x) + 0.5, 0);
        ctx.lineTo(Math.round(x) + 0.5, h);
        ctx.stroke();
      }
      for (let y = 0; y <= h; y += h / 4) {
        ctx.beginPath();
        ctx.moveTo(0, Math.round(y) + 0.5);
        ctx.lineTo(w, Math.round(y) + 0.5);
        ctx.stroke();
      }
      // trace
      const mid = h / 2;
      const isActive = activeRef.current;
      const data = levelsRef.current;
      ctx.strokeStyle = accent;
      ctx.shadowColor = accent;
      ctx.shadowBlur = 6;
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      const t = frame / 60;
      for (let x = 0; x <= w; x += 2) {
        let y: number;
        if (data && data.length) {
          const v = data[Math.floor((x / w) * (data.length - 1))] ?? 0;
          y = mid - v * (h * 0.45) * Math.sin(x * 0.25 + t * 8);
        } else if (isActive) {
          const env = Math.sin((x / w) * Math.PI);
          y = mid + env * (Math.sin(x * 0.08 + t * 9) * 0.6 + Math.sin(x * 0.21 - t * 5) * 0.25) * h * 0.32;
        } else {
          y = mid + (Math.random() - 0.5) * 1.6;
        }
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();
      ctx.shadowBlur = 0;
      frame += 1;
      if (animated()) raf = requestAnimationFrame(draw);
    };
    draw();
    const restart = window.setInterval(() => {
      if (animated() && !raf) raf = requestAnimationFrame(draw);
      if (!animated()) {
        cancelAnimationFrame(raf);
        raf = 0;
        draw();
      }
    }, 1000);
    return () => {
      cancelAnimationFrame(raf);
      window.clearInterval(restart);
    };
  }, []);

  return (
    <div className="scope">
      <canvas ref={canvasRef} aria-hidden="true" />
      <span className="scope__label mono-label">{label}</span>
    </div>
  );
}
