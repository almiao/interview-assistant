import type { QAPair } from '@/stores/configStore'

const usable = (qa: QAPair) => {
  const text = qa.answer.trim()
  return qa.status !== 'error' && qa.status !== 'cancelled' && Boolean(text)
    && (qa.status !== 'streaming' || text.length >= 4 || /[。！？.!?；;\n]/.test(text))
}

// Stay on one model for a question. A later/slow model must not replace text
// already being read. Only the newest question can take over the display.
export function selectCompactAnswer(pairs: QAPair[], previousId: string | null): QAPair | null {
  const newest = pairs[pairs.length - 1]
  if (!newest) return null
  const previous = pairs.find((qa) => qa.id === previousId && usable(qa))
  let groupStart = pairs.length - 1
  while (newest.questionSource !== 'algorithm_screen' && groupStart > 0 && pairs[groupStart - 1].question === newest.question) groupStart--
  const group = pairs.slice(groupStart)
  if (previous && group.some((qa) => qa.id === previous.id)) return previous
  const next = group.find(usable)
  return next ?? previous ?? [...pairs].reverse().find(usable) ?? null
}

export function compactAnswerText(answer: string, maxLines: number, columns: number) {
  // Preserve the prefix and code indentation; never skip/reorder streamed text.
  const lines = answer.replace(/\r\n/g, '\n').split('\n')
  let inCode = false
  let used = 0
  const result: string[] = []
  let omitted = false
  for (let index = 0; index < lines.length; index++) {
    const raw = lines[index]
    if (/^\s*```/.test(raw)) { inCode = !inCode; continue }
    const line = inCode ? raw : raw.replace(/^\s{0,3}#{1,6}\s+/, '').replace(/\*\*(.*?)\*\*/g, '$1')
    if (!line.trim()) continue
    // CJK characters occupy roughly twice the width of latin characters.
    const width = Array.from(line).reduce((n, char) => n + (/[^\x00-\xff]/.test(char) ? 2 : 1), 0)
    const cost = Math.max(1, Math.ceil(width / columns))
    if (used + cost > maxLines) {
      const remaining = (maxLines - used) * columns
      if (remaining > 0) {
        let count = 0
        let prefix = ''
        for (const char of line) {
          count += /[^\x00-\xff]/.test(char) ? 2 : 1
          if (count > Math.max(0, remaining - 2)) break
          prefix += char
        }
        result.push(`${prefix}…`)
      }
      omitted = true
      break
    }
    result.push(line)
    used += cost
  }
  return { text: result.join('\n'), omitted }
}
