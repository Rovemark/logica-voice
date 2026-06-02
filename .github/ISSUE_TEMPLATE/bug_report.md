---
name: Bug report
about: Something doesn't work the way it should
title: '[BUG] '
labels: bug
---

## Description
Clear, concise description of the bug.

## To Reproduce
Steps to reproduce:
1. Configure `logica-voice.yaml` with `...`
2. Run `logica-voice start`
3. Send message `...` on `<channel>`
4. See error

## Expected behavior
What should have happened.

## Actual behavior
What happened instead.

## Environment

- **Logica Voice version:** `0.x.y` (run `logica-voice --version`)
- **Node version:** `vXX.X.X` (run `node --version`)
- **OS:** macOS / Linux / Windows + version
- **Brain provider:** built-in / logicaos / openai / ...
- **Channels active:** telegram, whatsapp, voice, web

## Config (redact secrets!)

```yaml
# Paste relevant parts of logica-voice.yaml
# Remove API keys, phone numbers, tokens
```

## Logs

```
Paste output (DEBUG=logica-voice:* logica-voice start)
```

## Additional context
Screenshots, related issues, anything else useful.
