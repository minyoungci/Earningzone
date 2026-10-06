import { actionBg, actionLabel } from '../../lib/format'

export default function Badge({ action, children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${actionBg(action)} ${className}`}
    >
      {children || actionLabel(action)}
    </span>
  )
}
