import { useEffect, useRef, useState } from 'react'

import { api, type Box, type StreamLayout } from '../api'
import { ErrorNote } from './ErrorNote'

type Which = 'cam' | 'game'

const LABELS: Record<Which, string> = { cam: 'Streamer box', game: 'Gameplay box' }
const COLOURS: Record<Which, string> = {
  cam: 'border-sodium-400 bg-sodium-500/15',
  game: 'border-ink-100 bg-ink-100/10',
}

/**
 * Draw where the streamer's camera and the gameplay sit in a stream recording.
 *
 * Chop Shop detects the camera on its own; this is the fallback when it misses.
 * Pick a box, then drag across the frame to draw it. The overlay doesn't move,
 * so the boxes are saved once per video and reused for every clip.
 */
export function StreamLayoutEditor({ sourceId, t }: { sourceId: string; t: number }) {
  const [size, setSize] = useState<{ width: number; height: number } | null>(null)
  const [layout, setLayout] = useState<StreamLayout | null>(null)
  const [which, setWhich] = useState<Which>('cam')
  const [draft, setDraft] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(
    null,
  )
  const [busy, setBusy] = useState<'detect' | 'save' | null>(null)
  const [saved, setSaved] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const frame = useRef<HTMLDivElement>(null)

  useEffect(() => {
    api
      .getStreamLayout(sourceId)
      .then((result) => {
        setSize({ width: result.width, height: result.height })
        setLayout(result.layout)
      })
      .catch((err) => setError(err as Error))
  }, [sourceId])

  if (!size) return error ? <ErrorNote error={error} /> : null

  // Matches the server's default: the top 80%, leaving out the game's own
  // subtitles at the bottom (Chop Shop's captions replace them).
  const defaultGame: Box = { x: 0, y: 0, w: size.width, h: Math.round(size.height * 0.8) }
  const current: StreamLayout = layout ?? { cam: { x: 0, y: 0, w: 0, h: 0 }, game: defaultGame }

  /** Pointer position as source pixels. */
  const at = (e: React.PointerEvent) => {
    const rect = frame.current!.getBoundingClientRect()
    const clamp = (v: number) => Math.max(0, Math.min(1, v))
    return {
      x: clamp((e.clientX - rect.left) / rect.width) * size.width,
      y: clamp((e.clientY - rect.top) / rect.height) * size.height,
    }
  }

  const finish = () => {
    if (!draft) return
    const box: Box = {
      x: Math.round(Math.min(draft.x0, draft.x1)),
      y: Math.round(Math.min(draft.y0, draft.y1)),
      w: Math.round(Math.abs(draft.x1 - draft.x0)),
      h: Math.round(Math.abs(draft.y1 - draft.y0)),
    }
    setDraft(null)
    if (box.w < 20 || box.h < 20) return // a click, not a box
    setLayout({ ...current, [which]: box, origin: 'drawn' })
    setSaved(false)
    if (which === 'cam') setWhich('game') // natural next step
  }

  const run = async (kind: 'detect' | 'save', call: () => Promise<{ layout: StreamLayout | null }>) => {
    setBusy(kind)
    setError(null)
    try {
      const result = await call()
      setLayout(result.layout)
      setSaved(true)
      if (kind === 'detect' && !result.layout)
        setError(new Error("Couldn't find the streamer's camera. Draw the boxes instead."))
    } catch (err) {
      setError(err as Error)
    } finally {
      setBusy(null)
    }
  }

  const pct = (box: Box) => ({
    left: `${(box.x / size.width) * 100}%`,
    top: `${(box.y / size.height) * 100}%`,
    width: `${(box.w / size.width) * 100}%`,
    height: `${(box.h / size.height) * 100}%`,
  })
  const hasCam = current.cam.w > 0

  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap gap-2">
        {(['cam', 'game'] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setWhich(key)}
            className={['btn py-1 text-xs', which === key ? 'btn-primary' : 'btn-ghost'].join(' ')}
          >
            Draw {LABELS[key].toLowerCase()}
          </button>
        ))}
      </div>

      <div
        ref={frame}
        className="relative cursor-crosshair touch-none select-none overflow-hidden border border-ink-700"
        style={{ aspectRatio: `${size.width} / ${size.height}` }}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          const p = at(e)
          setDraft({ x0: p.x, y0: p.y, x1: p.x, y1: p.y })
        }}
        onPointerMove={(e) => {
          if (!draft) return
          const p = at(e)
          setDraft({ ...draft, x1: p.x, y1: p.y })
        }}
        onPointerUp={finish}
      >
        <img
          src={api.frameUrl(sourceId, t)}
          alt="A frame from the video to draw the boxes on"
          className="pointer-events-none absolute inset-0 size-full"
          draggable={false}
        />
        {(['game', 'cam'] as const).map(
          (key) =>
            (key === 'game' || hasCam) && (
              <div
                key={key}
                className={`pointer-events-none absolute border-2 ${COLOURS[key]}`}
                style={pct(current[key])}
              >
                <span className="absolute left-1 top-1 bg-ink-900/80 px-1 text-[10px] text-ink-100">
                  {LABELS[key]}
                </span>
              </div>
            ),
        )}
        {draft && (
          <div
            className="pointer-events-none absolute border-2 border-dashed border-sodium-400"
            style={pct({
              x: Math.min(draft.x0, draft.x1),
              y: Math.min(draft.y0, draft.y1),
              w: Math.abs(draft.x1 - draft.x0),
              h: Math.abs(draft.y1 - draft.y0),
            })}
          />
        )}
      </div>

      <p className="text-xs text-ink-500">
        {!hasCam
          ? 'No streamer box yet. Auto-detect, or draw it on the frame.'
          : layout?.origin === 'drawn'
            ? 'Using boxes you drew.'
            : 'Using the auto-detected streamer box. Redraw it if it looks off.'}{' '}
        The gameplay box is cropped to fit under the camera. Keep the game&apos;s own subtitles
        outside it; Chop Shop adds its own captions.
      </p>

      {error && <ErrorNote error={error} onDismiss={() => setError(null)} />}

      <div className="flex gap-2">
        <button
          type="button"
          className="btn btn-ghost flex-1 py-1 text-xs"
          disabled={busy !== null}
          onClick={() => run('detect', () => api.detectStreamLayout(sourceId))}
        >
          {busy === 'detect' ? 'Detecting… (~1 min)' : 'Auto-detect'}
        </button>
        <button
          type="button"
          className="btn btn-primary flex-1 py-1 text-xs"
          disabled={busy !== null || saved || !hasCam}
          onClick={() =>
            run('save', () => api.saveStreamLayout(sourceId, { cam: current.cam, game: current.game }))
          }
        >
          {busy === 'save' ? 'Saving…' : saved ? 'Saved' : 'Save boxes'}
        </button>
      </div>
    </div>
  )
}
