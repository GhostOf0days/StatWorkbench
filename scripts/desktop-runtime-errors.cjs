// Preserve renderer failures even when process output splits a message across chunks.
function createRuntimeErrorTracker() {
  const tails = new Map(), errors = [];
  function inspect(line) {
    if (/\[renderer:(?:error|3)\]|\[desktop-smoke\] renderer (?:stopped|failed to load)/.test(line) && errors.length < 50) errors.push(line.slice(0, 4096));
  }
  return {
    append(stream, chunk) {
      const lines = ((tails.get(stream) || '') + String(chunk)).split(/\r?\n/);
      tails.set(stream, lines.pop().slice(-8192));
      lines.forEach(inspect);
    },
    finish() {
      for (const tail of tails.values()) if (tail) inspect(tail);
      tails.clear();
      return [...errors];
    },
  };
}
module.exports = {createRuntimeErrorTracker};
