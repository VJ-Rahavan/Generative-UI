import { BarChart3, BookOpen, CalendarDays, ClipboardList, Salad, TrendingUp } from 'lucide-react'

const SUGGESTIONS = [
  { icon: BarChart3, title: 'Weekly summary', prompt: 'How did my training go this week?' },
  { icon: TrendingUp, title: 'Lift progress', prompt: 'How is my bench press progressing?' },
  {
    icon: CalendarDays,
    title: 'Build a program',
    prompt: 'Build me a 4-day upper/lower hypertrophy plan',
  },
  { icon: Salad, title: 'Calories & macros', prompt: 'Calculate my calories and macros for fat loss' },
  {
    icon: ClipboardList,
    title: 'Log a workout',
    prompt: 'Log today: squat 3x5 at 110 kg, RDL 3x8 at 90 kg, leg curl 3x12 at 45 kg',
  },
  { icon: BookOpen, title: 'Technique', prompt: 'How do I do a Romanian deadlift properly?' },
]

export function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col items-center px-4 pt-[12vh] pb-8 text-center">
      <img src="/favicon.svg" alt="" className="size-14" />
      <h1 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">
        What are we training today?
      </h1>
      <p className="mt-3 max-w-lg text-muted">
        Ask about your progress, plan a program or log a session. FitTrack answers with live
        dashboards, charts and forms built from your training data.
      </p>
      <div className="mt-10 grid w-full grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {SUGGESTIONS.map(({ icon: Icon, title, prompt }) => (
          <button
            key={title}
            onClick={() => onPick(prompt)}
            className="group flex flex-col items-start gap-2 rounded-2xl border border-border bg-surface p-4 text-left transition-colors hover:border-brand/40 hover:bg-surface-2"
          >
            <span className="grid size-8 place-items-center rounded-lg bg-brand/10 text-brand">
              <Icon className="size-4" />
            </span>
            <span className="text-sm font-semibold">{title}</span>
            <span className="text-sm text-muted group-hover:text-fg/80">{prompt}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
