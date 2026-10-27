import { Camera, Loader2 } from 'lucide-react'

export default function AlgorithmScreenButton({ onClick, busy, label, iconOnly = false }: {
  onClick: () => void
  busy: boolean
  label: string
  iconOnly?: boolean
}) {
  const Icon = busy ? Loader2 : Camera
  return (
    <button type="button" onClick={onClick} disabled={busy} aria-label={iconOnly ? '截屏' : '截屏解题'}
      title={iconOnly ? (busy ? '处理中' : '截屏') : '截取当前整屏，自动识别算法题并生成 Java 答案'}
      className="algorithm-screen-button inline-flex items-center gap-1.5 flex-shrink-0 rounded-lg px-2 py-1.5 text-xs text-accent-blue hover:bg-accent-blue/10 disabled:opacity-60 disabled:cursor-wait">
      <Icon aria-hidden="true" size={15} className={busy ? 'animate-spin' : ''} />
      {!iconOnly && <span aria-live="polite">{label}</span>}
    </button>
  )
}
