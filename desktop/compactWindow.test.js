const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { createCompactWindowController } = require('./compactWindow');

test('compact geometry can resize, persists, fits the active screen and restores normal geometry', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ia-compact-'));
  const file = path.join(dir, 'window.json');
  let bounds = { x: 100, y: 100, width: 1200, height: 800 };
  let minimum;
  let maximized = true;
  const events = {};
  const window = {
    on: (name, callback) => { events[name] = callback; },
    isDestroyed: () => false,
    isMaximized: () => maximized,
    getNormalBounds: () => ({ ...bounds }),
    getBounds: () => ({ ...bounds }),
    setBounds: (next) => { bounds = next; },
    setMinimumSize: (...size) => { minimum = size; },
    unmaximize: () => { maximized = false; },
    maximize: () => { maximized = true; },
  };
  const screen = { getDisplayMatching: () => ({ workArea: { x: 0, y: 0, width: 1600, height: 1000 } }) };
  try {
    fs.writeFileSync(file, JSON.stringify({ x: 3000, y: -100, width: 400, height: 250 }));
    const toggle = createCompactWindowController(window, screen, file);
    toggle(true);
    assert.deepEqual(minimum, [320, 200]);
    assert.deepEqual(bounds, { x: 1200, y: 0, width: 400, height: 250 });
    bounds = { x: 200, y: 300, width: 500, height: 400 };
    events.resized();
    assert.deepEqual(JSON.parse(fs.readFileSync(file)), bounds);
    toggle(false);
    assert.deepEqual(minimum, [800, 500]);
    assert.equal(maximized, true);
    assert.deepEqual(bounds, { x: 100, y: 100, width: 1200, height: 800 });
    toggle(true);
    assert.deepEqual(bounds, { x: 200, y: 300, width: 500, height: 400 });
    assert.throws(() => toggle('true'));
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
