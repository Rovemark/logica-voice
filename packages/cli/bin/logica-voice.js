#!/usr/bin/env node
import('../dist/index.js').then((m) => m.main(process.argv)).catch((err) => {
  console.error('[logica-voice] erro:', err?.message || err);
  process.exit(1);
});
