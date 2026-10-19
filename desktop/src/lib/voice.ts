import { useCallback, useEffect, useRef, useState } from "react";

// Mic recording + interviewer playback for the interview rooms.

const SPEECH_LEVEL = 0.04; // RMS above this counts as talking (hands-free mode)
const SILENCE_MS = 1800; // hands-free: stop after this long quiet, once you've spoken
const MAX_MS = 4 * 60 * 1000; // hard cap on one answer

const MODE_KEY = "interview.answerMode";

export function readAnswerMode(): "ptt" | "hands-free" {
  try {
    return localStorage.getItem(MODE_KEY) === "hands-free" ? "hands-free" : "ptt";
  } catch {
    return "ptt";
  }
}

export function saveAnswerMode(mode: "ptt" | "hands-free") {
  try {
    localStorage.setItem(MODE_KEY, mode);
  } catch {
    /* per-viewer convenience only */
  }
}

export type RecorderState = "idle" | "starting" | "recording";

/** Records one answer at a time as webm/opus. `level` (0..1) drives the meter.
 *  With handsFree, recording stops by itself after a pause and calls onAutoStop. */
export function useRecorder(opts: { handsFree?: boolean; onAutoStop?: (blob: Blob) => void } = {}) {
  const [state, setState] = useState<RecorderState>("idle");
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recRef = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const resolveRef = useRef<((b: Blob) => void) | null>(null);
  const rafRef = useRef(0);
  const ctxRef = useRef<AudioContext | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const finish = useCallback(() => {
    const rec = recRef.current;
    if (!rec || rec.state === "inactive") return Promise.resolve(new Blob());
    return new Promise<Blob>((resolve) => {
      resolveRef.current = resolve;
      rec.stop();
    });
  }, []);

  const start = useCallback(async () => {
    if (recRef.current?.state === "recording") return;
    setError(null);
    setState("starting");
    try {
      if (!streamRef.current) {
        streamRef.current = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
      }
    } catch (e) {
      setState("idle");
      setError(`Microphone unavailable: ${e instanceof Error ? e.message : e}`);
      return;
    }
    const stream = streamRef.current;
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    chunks.current = [];
    rec.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    rec.onstop = () => {
      cancelAnimationFrame(rafRef.current);
      source.disconnect();
      setLevel(0);
      setState("idle");
      const blob = new Blob(chunks.current, { type: "audio/webm" });
      const resolve = resolveRef.current;
      resolveRef.current = null;
      if (resolve) resolve(blob);
      else optsRef.current.onAutoStop?.(blob); // stopped by silence / time cap, not by the caller
    };
    recRef.current = rec;
    rec.start(250);
    setState("recording");

    // level meter + silence detection
    ctxRef.current ??= new AudioContext();
    const ctx = ctxRef.current;
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 1024;
    const source = ctx.createMediaStreamSource(stream);
    source.connect(analyser);
    const buf = new Float32Array(analyser.fftSize);
    const began = performance.now();
    let spoke = false;
    let lastLoud = began;
    const tick = () => {
      analyser.getFloatTimeDomainData(buf);
      const rms = Math.sqrt(buf.reduce((a, v) => a + v * v, 0) / buf.length);
      setLevel(Math.min(1, rms * 8));
      const now = performance.now();
      if (rms > SPEECH_LEVEL) {
        spoke = true;
        lastLoud = now;
      }
      const silent = optsRef.current.handsFree && spoke && now - lastLoud > SILENCE_MS;
      if ((silent || now - began > MAX_MS) && rec.state === "recording") {
        rec.stop();
        return;
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  /** Discards the current recording. */
  const cancel = useCallback(() => {
    const rec = recRef.current;
    if (rec && rec.state !== "inactive") {
      resolveRef.current = () => {};
      rec.stop();
    }
  }, []);

  useEffect(
    () => () => {
      cancel();
      cancelAnimationFrame(rafRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      ctxRef.current?.close().catch(() => {});
    },
    [cancel],
  );

  return { state, level, error, start, stop: finish, cancel };
}

/** Plays interviewer audio from the server, or speaks the text with the
 *  browser's own voices when the server has none (204 / failure). */
export function useSpeaker() {
  const [speaking, setSpeaking] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const runRef = useRef(0); // bumps on every play/stop so stale loads never start playing
  const doneRef = useRef<(() => void) | null>(null);

  const stop = useCallback(() => {
    runRef.current++;
    doneRef.current?.(); // settle a play() that was cut off, so its awaiter moves on
    audioRef.current?.pause();
    window.speechSynthesis?.cancel();
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    urlRef.current = null;
    setSpeaking(false);
  }, []);

  const play = useCallback(
    async (load: () => Promise<Blob | null>, fallbackText: string) => {
      stop();
      const run = runRef.current;
      setSpeaking(true);
      let blob: Blob | null = null;
      try {
        blob = await load();
      } catch {
        blob = null;
      }
      if (run !== runRef.current) return;
      await new Promise<void>((resolve) => {
        const done = () => {
          doneRef.current = null;
          resolve();
        };
        doneRef.current = done;
        if (blob) {
          const url = URL.createObjectURL(blob);
          urlRef.current = url;
          const audio = (audioRef.current ??= new Audio());
          audio.src = url;
          audio.onended = audio.onerror = () => done();
          audio.play().catch(() => done());
        } else if (window.speechSynthesis) {
          const u = new SpeechSynthesisUtterance(fallbackText);
          u.onend = u.onerror = () => done();
          window.speechSynthesis.speak(u);
        } else done();
      });
      if (run === runRef.current) setSpeaking(false);
    },
    [stop],
  );

  useEffect(() => stop, [stop]);
  return { speaking, play, stop };
}
