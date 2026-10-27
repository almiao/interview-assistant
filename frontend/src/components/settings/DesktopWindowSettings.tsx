import { useEffect, useState } from 'react'
import { Monitor } from 'lucide-react'
import { Section } from './shared'

export default function DesktopWindowSettings() {
  const api = window.electronAPI
  const [state, setState] = useState<{ alwaysOnTop: boolean; contentProtection: boolean } | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!api) return
    let active = true
    const refresh = () => {
      void api.getWindowState().then((value) => {
        if (active) { setState(value); setError('') }
      }).catch(() => { if (active) setError('窗口状态读取失败') })
    }
    refresh()
    window.addEventListener('focus', refresh)
    return () => { active = false; window.removeEventListener('focus', refresh) }
  }, [api])

  if (!api) return null

  async function toggle(key: 'alwaysOnTop' | 'contentProtection') {
    if (!api || pending) return
    setPending(true)
    setError('')
    try {
      const value = await (key === 'alwaysOnTop' ? api.toggleAlwaysOnTop() : api.toggleContentProtection())
      setState((previous) => previous ? { ...previous, [key]: value } : previous)
    } catch {
      setError('设置未生效，请重试')
    } finally {
      setPending(false)
    }
  }

  return (
    <Section title="桌面窗口" icon={<Monitor className="w-3.5 h-3.5" />} keywords="托盘 隐藏 置顶 屏幕共享 隐身">
      <div className="flex flex-wrap gap-4">
        {([['contentProtection', '屏幕共享隐身'], ['alwaysOnTop', '窗口置顶']] as const).map(([key, label]) => (
          <label key={key} className="flex items-center gap-2 text-xs text-text-secondary">
            <input type="checkbox" checked={state?.[key] ?? false} disabled={!state || pending}
              onChange={() => void toggle(key)} className="w-4 h-4 accent-accent-blue" />
            {label}
          </label>
        ))}
      </div>
      <p className="text-[11px] text-text-muted">托盘图标单击显示，再次单击隐藏。窗口设置本次运行有效。</p>
      {error && <p role="alert" className="text-xs text-accent-amber">{error}</p>}
    </Section>
  )
}
