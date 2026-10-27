const fs = require('fs');

function createCompactWindowController(window, screen, prefsPath) {
  let enabled = false;
  let normalBounds;
  let maximized = false;
  let compactBounds;
  try {
    const saved = JSON.parse(fs.readFileSync(prefsPath, 'utf8'));
    if (['x', 'y', 'width', 'height'].every((key) => Number.isFinite(saved[key]))
      && saved.width >= 320 && saved.height >= 200) compactBounds = saved;
  } catch { /* First use or invalid preference: use the default size. */ }

  function fit(bounds) {
    const area = screen.getDisplayMatching(bounds).workArea;
    const width = Math.min(area.width, bounds.width);
    const height = Math.min(area.height, bounds.height);
    return {
      width, height,
      x: Math.max(area.x, Math.min(bounds.x, area.x + area.width - width)),
      y: Math.max(area.y, Math.min(bounds.y, area.y + area.height - height)),
    };
  }
  function remember() {
    if (!enabled || window.isDestroyed()) return;
    compactBounds = window.getBounds();
    try { fs.writeFileSync(prefsPath, JSON.stringify(compactBounds)); } catch { /* Best effort. */ }
  }
  window.on('resized', remember);
  window.on('moved', remember);
  window.on('close', remember);
  return (next) => {
    if (typeof next !== 'boolean') throw new Error('Invalid compact mode');
    if (enabled === next) return;
    if (next) {
      maximized = window.isMaximized();
      normalBounds = window.getNormalBounds();
      if (maximized) window.unmaximize();
      window.setMinimumSize(320, 200);
      const bounds = fit(compactBounds || { ...normalBounds, width: 480, height: 360 });
      window.setBounds(bounds);
      enabled = true;
    } else {
      remember();
      enabled = false;
      window.setMinimumSize(800, 500);
      window.setBounds(fit(normalBounds));
      if (maximized) window.maximize();
    }
  };
}

module.exports = { createCompactWindowController };
