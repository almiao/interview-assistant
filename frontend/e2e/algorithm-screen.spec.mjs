import { test, expect } from '@playwright/test'
import { installMocks, COMMON_WS_BOOTSTRAP } from './fixtures/setup.mjs'

test('one-click Java screenshot answers work in full and compact views', async ({ context, page }) => {
  let requests = 0
  await installMocks(context, {
    messages: COMMON_WS_BOOTSTRAP,
    apiOverrides: (path) => {
      if (path === '/api/ask-algorithm-screen') return { ok: true, qa_id: `algorithm-${++requests}` }
    },
  })
  await context.addInitScript(() => {
    const Mock = window.WebSocket
    window.WebSocket = class extends Mock {
      constructor(...args) {
        super(...args)
        if (String(args[0]).split('?')[0].endsWith('/ws') && !window.__algorithmSocket) window.__algorithmSocket = this
      }
    }
  })
  const emit = (message) => page.evaluate((msg) => window.__algorithmSocket.onmessage(new MessageEvent('message', { data: JSON.stringify(msg) })), message)
  await page.goto('/')
  let button = page.getByRole('button', { name: '截屏解题', exact: true })
  await button.click()
  await expect(button).toBeDisabled()
  await expect(button).toContainText('识题解答中')
  expect(requests).toBe(1)
  await page.getByRole('button', { name: '进入精简模式' }).click()
  const compact = page.getByRole('region', { name: '精简视图' })
  await expect(compact).toBeVisible()
  button = compact.getByRole('button', { name: /^(截屏|处理中)$/ })
  await emit({ type: 'answer_start', id: 'algorithm-1', question: '截屏算法题 · Java', source: 'algorithm_screen', model_name: 'vision' })
  const answer = '使用哈希表记录已访问元素。\n```java\nimport java.util.*;\nclass Solution {\n' + '    // 保留完整代码\n'.repeat(30) + '    public int result() { return 42; }\n}\n```\n时间 O(n)，空间 O(n)。'
  await emit({ type: 'answer_done', id: 'algorithm-1', question: '截屏算法题 · Java', answer, think: '', model_name: 'vision' })
  await expect(button).toBeEnabled()
  await expect(page.getByLabel('核心答案')).toContainText('public int result()')
  for (const [width, height] of [[480, 360], [320, 200]]) {
    await page.setViewportSize({ width, height })
    await expect(button).toBeVisible()
    expect(await compact.evaluate((el) => el.scrollWidth <= el.clientWidth && el.scrollHeight <= el.clientHeight)).toBe(true)
    expect(await page.getByLabel('核心答案').evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true)
  }
  await page.screenshot({ path: 'test-results/algorithm-compact.png' })
  await button.click()
  await expect(button).toBeDisabled()
  expect(requests).toBe(2)
  await emit({ type: 'answer_start', id: 'algorithm-2', question: '截屏算法题 · Java', source: 'algorithm_screen' })
  await emit({ type: 'answer_done', id: 'algorithm-2', question: '截屏算法题 · Java', answer: '改用双指针。\n```java\nclass Solution {}\n```', think: '' })
  await expect(page.getByLabel('核心答案')).toContainText('改用双指针')
  await expect(button).toBeEnabled()
  await page.keyboard.press('Escape')
  await page.setViewportSize({ width: 1440, height: 900 })
  await expect(compact).not.toBeVisible()
  button = page.getByRole('button', { name: '截屏解题', exact: true })
  await expect(button).toBeVisible()
})
