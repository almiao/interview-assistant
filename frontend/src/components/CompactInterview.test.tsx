import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import CompactInterview from './CompactInterview'
import { useInterviewStore, type QAPair } from '@/stores/configStore'
import { compactAnswerText, selectCompactAnswer } from '@/lib/compactAnswer'

const qa = (id: string, question: string, answer = '', extra = {}): QAPair => ({
  id, question, answer, timestamp: 100, thinkContent: '', isThinking: false, status: answer ? 'done' : 'streaming', ...extra,
})

describe('compact interview live display', () => {
  beforeEach(() => {
    useInterviewStore.setState({ qaPairs: [], streamingIds: [], wsConnected: true, isRecording: true, isPaused: false, lastWSError: null })
  })

  it('keeps the old answer while thinking, switches when text arrives, and ignores late old-model output', () => {
    const first = qa('first', '什么是缓存？', '缓存复用已有结果。')
    useInterviewStore.setState({ qaPairs: [first] })
    render(<CompactInterview onExit={vi.fn()} />)
    expect(screen.getByLabelText('核心答案')).toHaveTextContent('缓存复用已有结果。')
    act(() => useInterviewStore.setState({ qaPairs: [first, qa('next', '缓存的缺点？', '', { isThinking: true })], streamingIds: ['next'] }))
    expect(screen.getByRole('status')).toHaveTextContent('更新中')
    expect(screen.getByLabelText('核心答案')).toHaveTextContent('缓存复用已有结果。')
    const next = qa('next', '缓存的缺点？', '需要处理一致性。', { status: 'streaming' })
    act(() => useInterviewStore.setState({ qaPairs: [first, next] }))
    expect(screen.getByLabelText('核心答案')).toHaveTextContent('需要处理一致性。')
    act(() => useInterviewStore.setState({ qaPairs: [{ ...first, answer: '旧模型补充' }, next, qa('other-model', next.question, '另一个模型输出')], streamingIds: [] }))
    expect(screen.getByLabelText('核心答案')).toHaveTextContent('需要处理一致性。')
  })

  it('shows disconnect, pause and generation errors without clearing readable content', () => {
    const first = qa('first', '问题', '已有回答')
    useInterviewStore.setState({ qaPairs: [first] })
    render(<CompactInterview onExit={vi.fn()} />)
    act(() => useInterviewStore.setState({ wsConnected: false }))
    expect(screen.getByRole('status')).toHaveTextContent('正在重连')
    act(() => useInterviewStore.setState({ wsConnected: true, isPaused: true }))
    expect(screen.getByRole('status')).toHaveTextContent('已暂停')
    act(() => useInterviewStore.setState({ isPaused: false, qaPairs: [first, qa('failed', '下一题', '', { status: 'error', errorMessage: '请求超时' })] }))
    expect(screen.getByRole('status')).toHaveTextContent('请求超时')
    expect(screen.getByLabelText('核心答案')).toHaveTextContent('已有回答')
    act(() => useInterviewStore.setState({ qaPairs: [] }))
    expect(screen.getByLabelText('核心答案')).not.toHaveTextContent('已有回答')
  })

  it('marks clipped content and preserves code indentation and the visible streamed prefix', () => {
    const prefix = '结论：优先使用缓存。\n- 注意失效时间。'
    expect(compactAnswerText(prefix, 10, 80).text).toBe(prefix)
    const clipped = compactAnswerText(prefix + '\n' + '补充'.repeat(200), 3, 30)
    expect(clipped.omitted).toBe(true)
    expect(clipped.text).toMatch(/^结论：优先使用缓存。/)
    expect(compactAnswerText('```python\nif x:\n    return x\n```', 10, 80).text).toBe('if x:\n    return x')
  })

  it('waits for a readable segment and does not reuse a historic answer when a question repeats', () => {
    const first = qa('first', '问题一', '旧答案。')
    const second = qa('second', '问题二', '第二题答案。')
    const repeated = qa('repeated', '问题一', '新', { status: 'streaming' })
    expect(selectCompactAnswer([first, second, repeated], second.id)?.id).toBe(second.id)
    expect(selectCompactAnswer([first, second, { ...repeated, answer: '新的回答。' }], second.id)?.id).toBe(repeated.id)
  })

  it('shows the full Java answer and switches between screenshot requests with the same label', () => {
    const first = qa('algorithm-1', '截屏算法题 · Java', '旧解答', { questionSource: 'algorithm_screen' })
    const second = qa('algorithm-2', first.question, '使用哈希表。\n```java\n' + '    // 代码\n'.repeat(80) + 'class Solution {}\n```', { questionSource: 'algorithm_screen' })
    expect(selectCompactAnswer([first, second], first.id)?.id).toBe(second.id)
    useInterviewStore.setState({ qaPairs: [first, second] })
    render(<CompactInterview onExit={vi.fn()} />)
    expect(screen.getByLabelText('核心答案')).toHaveTextContent('class Solution {}')
    expect(screen.getByLabelText('核心答案')).toHaveClass('compact-answer--algorithm')
    expect(screen.getByLabelText('滚动查看更多')).toBeVisible()
  })
})
