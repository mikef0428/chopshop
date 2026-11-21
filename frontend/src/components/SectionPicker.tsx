import { useRef, useState } from 'react'

import { api, formatDuration, type MomentsResult, type Section } from '../api'
import { ErrorNote } from './ErrorNote'

/** Ranges shorter than this from a drag are treated as a stray click. */
const MIN_DRAG_S = 5
/** Length of a range added with "Add range" when there is nothing to go on. */
const DEFAULT_RANGE_S = 600

/**
 * Pick which stretches of a long YouTube video to download.
 *
 * "Find popular moments" marks the parts viewers rewatch or talk about on a
 * timeline; click one to add it, or drag across the timeline to add your own.
 * Every range is also editable as text, so nothing depends on the mouse.
 */
export function SectionPicker({
  url,
  sections,
  onChange,
  disabled,
}: {
  url: string
  sections: Section[]
  onChange: (next: Section[]) => void
  disabled: boolean
}) {
  const [found, setFound] = useState<(MomentsResult & { url: string }) | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  // Moments belong to the URL they were found for.
  const result = found && found.url === url ? found : null
  const add = (s: Section) => onChange([...sections, s].sort((a, b) => a.start_s - b.start_s))
  const has = (s: Section) => sections.some((x) => x.start_s === s.start_s && x.end_s === s.end_s)
  const total = sections.reduce((sum, s) => sum + (s.end_s - s.start_s), 0)

  const findMoments = async () => {
    setLoading(true)
    setError(null)
    try {
      setFound({ ...(await api.findMoments(url)), url })
    } catch (err) {
      setError(err as Error)
    } finally {
      setLoading(false)
    }
  }

  const addBlank = () => {
    const start = sections.length ? sections[sections.length - 1].end_s : 0
    const end = start + DEFAULT_RANGE_S
    add({ start_s: start, end_s: result ? Math.min(end, result.duration_s) : end })
  }

  return (
    <div className="mt-8">
      <p className="eyebrow">Only part of the video? (optional)</p>
      <div className="mt-3 flex flex-wrap gap-3">
        <button
          type="button"
          className="btn"
          onClick={findMoments}
          disabled={disabled || loading || !url.trim()}
        >
          {loading ? 'Reading replays and comments…' : 'Find popular moments'}
        </button>
        <button type="button" className="btn btn-quiet" onClick={addBlank} disabled={disabled}>
          + Add range
        </button>
      </div>

      {error && (
        <div className="mt-4">
          <ErrorNote error={error} onDismiss={() => setError(null)} />
        </div>
      )}

      {result && (
        <>
          <Timeline
            duration={result.duration_s}
            moments={result.moments}
            sections={sections}
            onAdd={add}
            disabled={disabled}
          />
          {result.moments.length === 0 ? (
            <p className="mt-3 text-xs text-ink-500">
              No popular moments found: no replay data and no timestamps in the top comments.
              Drag across the timeline to pick ranges yourself.
            </p>
          ) : (
            <ul className="mt-3 divide-y divide-ink-800 text-sm">
              {result.moments.map((m) => (
                <li key={`${m.start_s}-${m.end_s}`} className="flex items-start gap-3 py-2">
                  <span className="numeric w-36 shrink-0 text-ink-200">
                    {formatDuration(m.start_s)}–{formatDuration(m.end_s)}
                  </span>
                  <span className="min-w-0 flex-1 text-ink-400">
                    {m.flagged && (
                      <span className="mr-2 text-sodium-600" title="Comments suggest nudity">
                        ⚠ likely NSFW
                      </span>
                    )}
                    {m.quotes[0] ?? (m.source === 'replays' ? 'Most replayed' : '')}
                  </span>
                  <button
                    type="button"
                    className="btn btn-quiet shrink-0 py-0"
                    onClick={() => add({ start_s: m.start_s, end_s: m.end_s })}
                    disabled={disabled || has(m)}
                  >
                    {has(m) ? 'Added' : '+ Add'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      {sections.length > 0 && (
        <div className="mt-5">
          <p className="text-xs text-ink-500">
            Downloading {sections.length} range{sections.length === 1 ? '' : 's'} ·{' '}
            {formatDuration(total)} total, joined into one video.
          </p>
          <ul className="mt-2 space-y-2">
            {sections.map((s, i) => (
              <li key={i} className="flex items-center gap-3 text-sm">
                <ClockField
                  label={`Range ${i + 1} start`}
                  value={s.start_s}
                  onCommit={(v) => onChange(replace(sections, i, { ...s, start_s: v }))}
                  disabled={disabled}
                />
                <span className="text-ink-500">to</span>
                <ClockField
                  label={`Range ${i + 1} end`}
                  value={s.end_s}
                  onCommit={(v) => onChange(replace(sections, i, { ...s, end_s: v }))}
                  disabled={disabled}
                />
                {s.end_s <= s.start_s && <span className="text-sodium-600">ends before it starts</span>}
                <button
                  type="button"
                  className="btn btn-quiet ml-auto py-0"
                  aria-label={`Remove range ${i + 1}`}
                  onClick={() => onChange(sections.filter((_, j) => j !== i))}
                  disabled={disabled}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Timeline({
  duration,
  moments,
  sections,
  onAdd,
  disabled,
}: {
  duration: number
  moments: MomentsResult['moments']
  sections: Section[]
  onAdd: (s: Section) => void
  disabled: boolean
}) {
  const bar = useRef<HTMLDivElement>(null)
  const [draft, setDraft] = useState<{ from: number; to: number } | null>(null)

  const timeAt = (clientX: number) => {
    const rect = bar.current!.getBoundingClientRect()
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) * duration
  }
  const pct = (t: number) => `${(t / duration) * 100}%`
  const span = (a: number, b: number) => ({ left: pct(a), width: pct(Math.max(0, b - a)) })

  return (
    <div className="mt-5">
      <div
        ref={bar}
        className="relative h-14 cursor-crosshair touch-none select-none border border-ink-700 bg-ink-850"
        onPointerDown={(e) => {
          if (disabled || duration <= 0) return
          e.currentTarget.setPointerCapture(e.pointerId)
          const t = timeAt(e.clientX)
          setDraft({ from: t, to: t })
        }}
        onPointerMove={(e) => draft && setDraft({ ...draft, to: timeAt(e.clientX) })}
        onPointerUp={() => {
          if (draft && Math.abs(draft.to - draft.from) >= MIN_DRAG_S) {
            const [a, b] = [draft.from, draft.to].sort((x, y) => x - y)
            onAdd({ start_s: Math.round(a), end_s: Math.round(b) })
          }
          setDraft(null)
        }}
      >
        {moments.map((m) => (
          <button
            key={`${m.start_s}-${m.end_s}`}
            type="button"
            title={`${formatDuration(m.start_s)}–${formatDuration(m.end_s)}${m.quotes[0] ? ` · ${m.quotes[0]}` : ''}`}
            className={[
              'absolute top-0 h-full min-w-1.5',
              m.flagged ? 'bg-ink-600/70' : 'bg-sodium-700/60 hover:bg-sodium-600/80',
            ].join(' ')}
            style={span(m.start_s, m.end_s)}
            // Click to add; stop the bar from starting a drag underneath.
            onPointerDown={(e) => e.stopPropagation()}
            onClick={() => !disabled && onAdd({ start_s: m.start_s, end_s: m.end_s })}
          />
        ))}
        {sections.map((s, i) => (
          <div
            key={i}
            className="pointer-events-none absolute bottom-0 h-1/3 border-x border-sodium-400 bg-sodium-500/70"
            style={span(s.start_s, s.end_s)}
          />
        ))}
        {draft && (
          <div
            className="pointer-events-none absolute top-0 h-full bg-sodium-400/30"
            style={span(Math.min(draft.from, draft.to), Math.max(draft.from, draft.to))}
          />
        )}
      </div>
      <div className="numeric mt-1 flex justify-between text-xs text-ink-500">
        <span>0:00</span>
        <span>Drag to add a range · click a highlight to add it</span>
        <span>{formatDuration(duration)}</span>
      </div>
    </div>
  )
}

function ClockField({
  label,
  value,
  onCommit,
  disabled,
}: {
  label: string
  value: number
  onCommit: (seconds: number) => void
  disabled: boolean
}) {
  return (
    <input
      // Re-mount when the value changes elsewhere so the text stays in sync.
      key={value}
      aria-label={label}
      className="field numeric w-28 py-1 text-sm"
      defaultValue={formatDuration(value)}
      disabled={disabled}
      onBlur={(e) => {
        const seconds = parseClock(e.target.value)
        if (seconds === null) e.target.value = formatDuration(value)
        else if (seconds !== value) onCommit(seconds)
      }}
      onKeyDown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
    />
  )
}

/** "1:02:03", "62:03" or "3723" → seconds; null if it isn't a time. */
export function parseClock(text: string): number | null {
  const parts = text.trim().split(':')
  if (parts.length > 3 || parts.some((p) => !/^\d+$/.test(p))) return null
  return parts.reduce((total, p) => total * 60 + Number(p), 0)
}

function replace<T>(items: T[], index: number, item: T): T[] {
  return items.map((x, i) => (i === index ? item : x))
}
