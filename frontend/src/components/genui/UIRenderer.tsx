import type { ComponentType } from 'react'
import type { UINode, UINodeType } from '../../types/ui'
import { ComponentErrorBoundary } from './ErrorBoundary'
import { AlertView } from './components/AlertView'
import { ButtonView } from './components/ButtonView'
import { CardView } from './components/CardView'
import { ChartView } from './components/ChartView'
import { ExerciseCardView } from './components/ExerciseCardView'
import { FormView } from './components/FormView'
import { LayoutView } from './components/LayoutView'
import { ListView } from './components/ListView'
import { MetricView } from './components/MetricView'
import { ProgressView } from './components/ProgressView'
import { TableView } from './components/TableView'
import { TextView } from './components/TextView'
import { TimerView } from './components/TimerView'
import { WorkoutPlanView } from './components/WorkoutPlanView'

type Registry = { [K in UINodeType]: ComponentType<{ node: Extract<UINode, { type: K }> }> }

/** One renderer per component type in the backend catalog. */
const registry: Registry = {
  text: TextView,
  metric: MetricView,
  card: CardView,
  layout: LayoutView,
  table: TableView,
  chart: ChartView,
  list: ListView,
  alert: AlertView,
  progress: ProgressView,
  button: ButtonView,
  form: FormView,
  exercise_card: ExerciseCardView,
  workout_plan: WorkoutPlanView,
  timer: TimerView,
}

export function UINodeView({ node }: { node: UINode }) {
  const View = registry[node.type] as ComponentType<{ node: UINode }> | undefined
  if (!View) {
    return (
      <div className="rounded-xl border border-dashed border-border px-4 py-3 text-sm text-muted">
        Unsupported component: <code>{String((node as { type?: unknown }).type)}</code>
      </div>
    )
  }
  return (
    <ComponentErrorBoundary name={node.type}>
      <View node={node} />
    </ComponentErrorBoundary>
  )
}

export function UIRenderer({ components }: { components: UINode[] }) {
  return (
    <div className="flex flex-col gap-4">
      {components.map((node, i) => (
        <UINodeView key={i} node={node} />
      ))}
    </div>
  )
}
