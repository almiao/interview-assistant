import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DesktopWindowSettings from './DesktopWindowSettings'

const originalApi = window.electronAPI
afterEach(() => { window.electronAPI = originalApi })

describe('desktop window settings', () => {
  it('reads native state, applies changes, and refreshes after focus returns', async () => {
    const getWindowState = vi.fn().mockResolvedValue({ contentProtection: true, alwaysOnTop: false, visible: true })
    const toggleContentProtection = vi.fn().mockResolvedValue(false)
    const toggleAlwaysOnTop = vi.fn().mockResolvedValue(true)
    window.electronAPI = { getWindowState, toggleContentProtection, toggleAlwaysOnTop } as any
    render(<DesktopWindowSettings />)
    const protection = screen.getByRole('checkbox', { name: '屏幕共享隐身' })
    const pinned = screen.getByRole('checkbox', { name: '窗口置顶' })
    await waitFor(() => expect(protection).toBeChecked())
    fireEvent.click(protection)
    await waitFor(() => expect(protection).not.toBeChecked())
    expect(toggleContentProtection).toHaveBeenCalledTimes(1)
    fireEvent.click(pinned)
    await waitFor(() => expect(pinned).toBeChecked())
    expect(toggleAlwaysOnTop).toHaveBeenCalledTimes(1)
    fireEvent(window, new Event('focus'))
    await waitFor(() => expect(protection).toBeChecked())
    expect(pinned).not.toBeChecked()
  })

  it('keeps the previous value if a native change fails and allows retry', async () => {
    const toggleContentProtection = vi.fn().mockRejectedValueOnce(new Error('failed')).mockResolvedValue(false)
    window.electronAPI = {
      getWindowState: vi.fn().mockResolvedValue({ contentProtection: true, alwaysOnTop: false, visible: true }),
      toggleContentProtection,
    } as any
    render(<DesktopWindowSettings />)
    const protection = screen.getByRole('checkbox', { name: '屏幕共享隐身' })
    await waitFor(() => expect(protection).toBeChecked())
    fireEvent.click(protection)
    expect(await screen.findByRole('alert')).toHaveTextContent('设置未生效')
    expect(protection).toBeChecked()
    expect(protection).toBeEnabled()
    fireEvent.click(protection)
    await waitFor(() => expect(protection).not.toBeChecked())
  })

  it('does not show desktop controls in a regular browser', () => {
    window.electronAPI = undefined
    render(<DesktopWindowSettings />)
    expect(screen.queryByText('桌面窗口')).not.toBeInTheDocument()
  })
})
