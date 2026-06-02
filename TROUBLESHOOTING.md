# Troubleshooting

Common issues and fixes. If your problem isn't here, [open an issue](https://github.com/Rovemark/logica-voice/issues/new/choose).

---

## Installation

### `pnpm install` fails with `ERR_PNPM_UNSUPPORTED_ENGINE`

You need **Node 20+**. Check:
```bash
node --version   # should be v20.x or higher
```

Install with [nvm](https://github.com/nvm-sh/nvm):
```bash
nvm install 20
nvm use 20
```

### `pnpm: command not found`

```bash
npm install -g pnpm@9
# or:
corepack enable && corepack prepare pnpm@9 --activate
```

### Build fails: `Cannot find module '@logica-voice/core'`

You need to build `@logica-voice/core` first (other packages depend on its `.d.ts`):

```bash
pnpm -r build   # builds in topological order
```

---

## Telegram adapter

### Bot doesn't respond to messages

1. **Check ACL:** in `logica-voice.yaml`, your user_id must be in `allowedChatIds`. Discover yours with [@userinfobot](https://t.me/userinfobot).

   ```yaml
   channels:
     telegram:
       allowedChatIds: ["123456789"]   # your user_id as string
   ```

2. **Empty allowlist = deny all** (fail-closed). Set `allowAll: true` only for testing (NOT prod).

### `[telegram] 409 conflict — outro processo polling`

Two processes are polling the same bot. Telegram only allows one. Stop the duplicate:

```bash
ps aux | grep logica-voice
kill <duplicate_pid>
```

Or you have an active webhook — remove it:
```bash
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"
```

### Token shows in logs

Never commit `.env`. Check `.gitignore` includes `.env*`.

---

## WhatsApp adapter

### QR code doesn't appear

1. Check `authDir` permissions — Logica Voice needs write access:
   ```bash
   mkdir -p ./.wa-auth
   chmod 700 ./.wa-auth
   ```

2. Already paired? Delete and re-scan:
   ```bash
   rm -rf ./.wa-auth
   # restart, QR appears in terminal
   ```

### `🔴 LOGOUT (401)` — process exits

You logged out from another device (WhatsApp Web/another bot stole the session).

```bash
rm -rf ./.wa-auth
# restart, scan QR again
```

### Bot ignores messages from me

**Check ACL.** Logica Voice is **fail-closed** by design:

```yaml
channels:
  whatsapp:
    allowedPhones:
      - "+5585991420169"   # your phone with country code
```

Both formats work (with/without 9th digit for BR):
- `+5585991420169` (13 digits, with 9)
- `+558591420169` (12 digits, without 9)

If your sender appears as `@lid` (no resolvable phone), add to `allowedLids`:
```yaml
allowedLids:
  - "28596160745525@lid"
```

### Bot responds in groups but I don't want it to

Group mention detection is automatic, but you need to `@<botname>` for it to respond. Configure in your brain prompt to ignore unless mentioned.

### Baileys version mismatch warnings

Baileys updates frequently. Pin to a known-good version in `package.json`:
```json
"@whiskeysockets/baileys": "6.17.16"
```

Then `pnpm install`.

---

## Brain adapters

### `built-in` brain: `LLM HTTP 401`

Your API key is wrong/expired. Check:
```bash
echo $OPENAI_API_KEY    # should print sk-...
```

Set in `.env`:
```bash
OPENAI_API_KEY=sk-yourkey
```

Or directly in `logica-voice.yaml`:
```yaml
brain:
  defaultLlm:
    provider: openai
    model: gpt-4o
    apiKey: sk-yourkey      # don't commit this!
```

### `logicaos` brain: `LogicaOS brain unreachable`

LogicaOS must be running:
```bash
# check
curl http://localhost:3001/api/health   # should return {"ok":true}
```

If not, start LogicaOS first. Config:
```yaml
brain:
  provider: logicaos
  url: http://localhost:3001
  apiKey: ${BRAIN_API_KEY}      # from LogicaOS .env
```

### Multi-agent mention not working

In `agents.yaml`, slugs must be lowercase + use hyphens:
```yaml
agents:
  - slug: copywriter       # ✅
  - slug: copy-writer      # ✅
  - slug: CopyWriter       # ❌ won't match @copywriter
```

---

## Voice services (v0.2 preview)

### `FasterWhisperSTT: implementação completa em v0.2`

Voice services are stubs in v0.1. Full implementation comes in v0.2. For now, use text-only channels.

### Python dependencies missing (when v0.2 ships)

You'll need Python 3.10+ and:
```bash
pip install faster-whisper websockets
# Apple Silicon: also `mlx-whisper` for better perf
```

---

## Performance

### High RAM usage

Default models load lazy. RAM by component:
- Core only: ~50MB
- + Telegram + WhatsApp adapters: ~80MB
- + faster-whisper large-v3: +3GB
- + Kokoro: +200MB
- + F5-TTS (when loaded): +2GB
- + Moshi MLX: +14GB

Run only what you need. Disable unused services in `logica-voice.yaml`.

### High latency

- **Brain provider:** cloud LLMs have 300-800ms first-token latency. Use Ollama/MLX local for <300ms.
- **TTS first chunk:** Kokoro ~80ms, F5-TTS ~250ms. Kokoro for quick responses.
- **STT:** faster-whisper large-v3 = ~250ms. Use smaller models (base/small) for ~100ms.

---

## Debug

### Enable verbose logs

```bash
DEBUG=logica-voice:* logica-voice start
```

### Inspect frame flow (v0.2)

Coming in v0.2: `LV_TRACE_FRAMES=1` will log every frame as it flows through the pipeline.

### Check what's running

```bash
logica-voice status
```

Or via PM2 if you wrapped it:
```bash
pm2 list
pm2 logs logica-voice
```

---

## Still stuck?

- **Search existing issues:** https://github.com/Rovemark/logica-voice/issues
- **Open a new issue:** use the [bug report template](.github/ISSUE_TEMPLATE/bug_report.md)
- **Include:** Node version, OS, your `logica-voice.yaml` (redact secrets), full error stack
