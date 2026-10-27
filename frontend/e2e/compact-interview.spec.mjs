import { test, expect } from '@playwright/test'
import { installMocks, COMMON_WS_BOOTSTRAP } from './fixtures/setup.mjs'

test('compact mode fits small windows, follows new questions, and exits without stopping the session', async ({ context, page }) => {
  const errors = []
  page.on('pageerror', (error) => errors.push(String(error)))
  await installMocks(context, {
    messages: [
      ...COMMON_WS_BOOTSTRAP,
      { type: 'init', delay: 50, is_recording: true, is_paused: false, stt_loaded: true,
        qa_pairs: [{ id: 'first', question: 'Redis 缓存如何保证一致性？', answer: '优先采用先更新数据库、再删除缓存的策略。\n- 缓存设置合理的过期时间。\n- 删除失败时使用重试机制。\n- 高一致性场景需要额外协调。\n' + '详细解释与示例。'.repeat(160), timestamp: 100 }] },
    ],
    localStorage: { 'ia-color-scheme': 'vscode-light-plus' },
  })
  await context.addInitScript(() => {
    const Mock = window.WebSocket
    window.WebSocket = class extends Mock {
      constructor(...args) {
        super(...args)
        if (String(args[0]).split('?')[0].endsWith('/ws') && !window.__compactSocket) window.__compactSocket = this
      }
    }
  })
  await page.goto('/')
  await expect(page.getByText('REC', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '进入精简模式' }).click()
  const compact = page.getByRole('region', { name: '精简视图' })
  await expect(compact).toBeVisible()
  await expect(page.getByLabel('核心答案')).toContainText('优先采用先更新数据库')
  for (const [width, height] of [[480, 360], [320, 200], [700, 480]]) {
    await page.setViewportSize({ width, height })
    await expect(page.getByRole('button', { name: '退出精简模式' })).toBeVisible()
    await expect(page.getByLabel('展开查看全文')).toBeVisible()
    expect(await compact.evaluate((el) => el.scrollWidth <= el.clientWidth && el.scrollHeight <= el.clientHeight)).toBe(true)
    await page.screenshot({ path: `test-results/compact-${width}x${height}.png` })
  }
  await page.evaluate(() => window.__compactSocket.onmessage(new MessageEvent('message', { data: JSON.stringify({ type: 'answer_start', id: 'followup', question: '删除失败怎么办？' }) })))
  await expect(page.getByRole('status')).toContainText('更新中')
  await expect(page.getByLabel('核心答案')).toContainText('优先采用先更新数据库')
  await page.evaluate(() => window.__compactSocket.onmessage(new MessageEvent('message', { data: JSON.stringify({ type: 'answer_chunk', id: 'followup', chunk: '使用重试队列，必要时结合补偿机制。' }) })))
  await expect(page.getByLabel('核心答案')).toHaveText('使用重试队列，必要时结合补偿机制。')
  await page.keyboard.press('Escape')
  await expect(compact).not.toBeVisible()
  await page.setViewportSize({ width: 1200, height: 800 })
  await expect(page.getByText('REC', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '进入精简模式' })).toBeVisible()
  expect(errors).toEqual([])
})
