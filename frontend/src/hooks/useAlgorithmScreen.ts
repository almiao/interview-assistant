import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import { useInterviewStore } from '@/stores/configStore'

export function useAlgorithmScreen() {
  const [capturing, setCapturing] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const locked = useRef(false)
  const revision = useRef(0)
  const active = useInterviewStore((s) => s.qaPairs.find((qa) => qa.id === activeId))
  const connected = useInterviewStore((s) => s.wsConnected)
  const reset = useCallback(() => {
    revision.current++
    locked.current = false
    setCapturing(false)
    setActiveId(null)
  }, [])

  useEffect(() => useInterviewStore.subscribe((state, previous) => {
    if (state.qaPairs !== previous.qaPairs && state.qaPairs.length === 0) reset()
  }), [reset])
  useEffect(() => {
    if (active && ['done', 'error', 'cancelled'].includes(active.status ?? '')) {
      if (active.status === 'error') setError(active.errorMessage || '算法解题失败，请重试')
      locked.current = false
      setActiveId(null)
    }
  }, [active])
  useEffect(() => {
    if (!connected && locked.current) {
      setError('连接已中断，请恢复连接后重新截屏解题')
      reset()
    }
  }, [connected, reset])

  const capture = useCallback(async () => {
    if (locked.current) return
    if (!useInterviewStore.getState().wsConnected) {
      setError('连接已中断，请恢复连接后重新截屏解题')
      return
    }
    locked.current = true
    const current = ++revision.current
    setError(null)
    setCapturing(true)
    try {
      const result = await api.askAlgorithmScreen()
      if (revision.current === current) {
        // 单模型忙时任务会排队；建立占位让取消/清空也能结束等待。
        const store = useInterviewStore.getState()
        if (!store.qaPairs.some((qa) => qa.id === result.qa_id)) {
          store.startAnswer(result.qa_id, '截屏算法题 · Java', { source: 'algorithm_screen' })
        }
        setActiveId(result.qa_id)
      }
    } catch (cause) {
      if (revision.current !== current) return
      const message = cause instanceof Error ? cause.message : '截屏解题失败，请重试'
      setError(message)
      useInterviewStore.getState().pushToast(message, 'error')
      locked.current = false
    } finally {
      if (revision.current === current) setCapturing(false)
    }
  }, [])

  return {
    capture,
    busy: capturing || activeId !== null,
    label: capturing ? '正在截屏…' : activeId ? (active?.answer ? '生成答案…' : '识题解答中…') : '截屏解题',
    error,
  }
}
