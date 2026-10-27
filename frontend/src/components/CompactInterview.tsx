import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { AlertCircle, Ellipsis, FileText, History, Loader2, Maximize2, Mic, MicOff, Minus, Pause, ScanLine, WifiOff } from 'lucide-react'
import { useInterviewStore } from '@/stores/configStore'
import { compactAnswerText, selectCompactAnswer } from '@/lib/compactAnswer'
import AlgorithmScreenButton from './AlgorithmScreenButton'
import type { useAlgorithmScreen } from '@/hooks/useAlgorithmScreen'

export default function CompactInterview({ onExit, algorithmScreen }: { onExit: () => void; algorithmScreen?: ReturnType<typeof useAlgorithmScreen> }) {
  const pairs = useInterviewStore((s) => s.qaPairs)
  const connected = useInterviewStore((s) => s.wsConnected)
  const recording = useInterviewStore((s) => s.isRecording)
  const paused = useInterviewStore((s) => s.isPaused)
  const lastError = useInterviewStore((s) => s.lastWSError)
  const streamingIds = useInterviewStore((s) => s.streamingIds)
  const previousId = useRef<string | null>(null)
  const answer = selectCompactAnswer(pairs, previousId.current)
  useEffect(() => { previousId.current = answer?.id ?? null }, [answer?.id])
  const latest = pairs[pairs.length - 1]
  const pending = latest && (latest.questionSource === 'algorithm_screen' ? answer?.id !== latest.id : answer?.question !== latest.question)
  const algorithmAnswer = answer?.questionSource === 'algorithm_screen'
  const failed = latest?.status === 'error' || latest?.status === 'cancelled'
  const contentRef = useRef<HTMLDivElement>(null)
  const [capacity, setCapacity] = useState({ lines: 10, columns: 48 })
  const [clipped, setClipped] = useState(false)
  useLayoutEffect(() => {
    const element = contentRef.current
    if (!element) return
    const measure = () => {
      if (!element.clientWidth || !element.clientHeight) return
      setCapacity({ lines: Math.max(1, Math.floor((element.clientHeight - 10) / 26)), columns: Math.max(8, Math.floor(element.clientWidth / 8.5)) })
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  const excerpt = compactAnswerText(answer?.answer ?? '', capacity.lines, capacity.columns)
  useLayoutEffect(() => {
    const el = contentRef.current
    setClipped(Boolean(el && el.scrollHeight > el.clientHeight + 1))
  }, [excerpt.text, capacity])
  const status = !connected ? '正在重连'
    : lastError ? lastError
    : algorithmScreen?.busy ? '处理中'
    : !recording ? '待机'
    : paused ? '已暂停'
    : failed ? (latest.errorMessage || (latest.status === 'cancelled' ? '已取消' : '处理失败'))
    : pending || (answer && streamingIds.includes(answer.id)) ? '更新中'
    : '接收中'
  const warning = !connected || Boolean(lastError) || (!algorithmScreen?.busy && (paused || failed || !recording))
  const StatusIcon = !connected ? WifiOff
    : lastError ? AlertCircle
    : algorithmScreen?.busy ? Loader2
    : !recording ? MicOff
    : paused ? Pause
    : failed ? AlertCircle
    : pending || (answer && streamingIds.includes(answer.id)) ? Loader2
    : Mic
  const question = algorithmAnswer || (!answer && latest?.questionSource === 'algorithm_screen')
    ? '屏幕摘录' : answer?.question || latest?.question
  const truncated = !algorithmAnswer && (excerpt.omitted || clipped)

  return (
    <section className="compact-interview" aria-label="精简视图">
      <header className="app-drag-region compact-toolbar">
        <span className={`compact-status ${warning ? 'compact-status--warning' : ''}`} role="status" title={status}>
          <StatusIcon size={14} aria-hidden="true" className={StatusIcon === Loader2 ? 'animate-spin' : undefined} />
          <span className="sr-only">{status}</span>
        </span>
        {algorithmScreen && <AlgorithmScreenButton onClick={() => void algorithmScreen.capture()} busy={algorithmScreen.busy} label={algorithmScreen.label} iconOnly />}
        {window.electronAPI && <button aria-label="最小化窗口" title="最小化" onClick={() => window.electronAPI?.minimizeWindow()}><Minus size={15} /></button>}
        <button onClick={onExit} aria-label="退出精简模式" title="展开 (Esc)"><Maximize2 size={15} /></button>
      </header>
      {question && <div className="compact-question" title={question}>
        {pending && answer && <span className="compact-previous" title="上一条"><History size={12} aria-label="上一条" /></span>}
        {question}
      </div>}
      {algorithmScreen?.error && <div className="compact-notice text-accent-amber" role="alert">{algorithmScreen.error}</div>}
      <div ref={contentRef} className={`compact-answer${algorithmAnswer ? ' compact-answer--algorithm' : ''}`} aria-label="核心答案">
        {(algorithmAnswer ? compactAnswerText(answer.answer, Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER).text : excerpt.text) || <span className="compact-empty text-text-muted"><FileText size={22} aria-hidden="true" />{algorithmScreen?.busy || latest?.isThinking ? '处理中…' : '暂无内容'}</span>}
      </div>
      {answer?.visionVerify && answer.visionVerify.verdict !== 'PASS' && <div className="compact-notice text-accent-amber"><AlertCircle size={12} aria-hidden="true" /> 待核对</div>}
      {(algorithmAnswer || truncated) && <footer className="compact-notice" title={algorithmAnswer ? '滚动查看更多' : '展开查看全文'} aria-label={algorithmAnswer ? '滚动查看更多' : '展开查看全文'}>
        {algorithmAnswer ? <ScanLine size={13} aria-hidden="true" /> : <Ellipsis size={15} aria-hidden="true" />}
      </footer>}
    </section>
  )
}
