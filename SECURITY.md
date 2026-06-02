# Security Policy

## Supported Versions

Logica Voice is in early development (v0.x). Only the **latest minor version** receives security fixes.

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅ |
| < 0.1   | ❌ |

When v1.0 ships, we'll publish a longer-term support policy.

## Reporting a Vulnerability

**Please do NOT open a public issue for security vulnerabilities.**

Email: **sirambrosio@gmail.com** with subject `[SECURITY] Logica Voice — <short description>`

Include:
- Description of the vulnerability
- Steps to reproduce (or proof-of-concept code)
- Affected version(s)
- Suggested fix (optional)
- Your contact info for follow-up

## What to expect

- **Within 48 hours:** acknowledgment that we received your report
- **Within 7 days:** initial assessment and severity classification
- **Within 30 days:** fix released (for critical/high severity) or detailed mitigation plan

We'll credit you in the release notes unless you prefer anonymity.

## Security-sensitive areas

These parts of Logica Voice handle sensitive data — please pay extra attention:

### 🔐 Channel adapters
- **WhatsApp** (`@logica-voice/adapter-whatsapp`): handles auth credentials in `authDir`. ACL is fail-closed by design — bypassing it is a security bug.
- **Telegram** (`@logica-voice/adapter-telegram`): bot token in env. ACL check on `allowedChatIds`.

### 🎙 Voice cloning
- **Voice embeddings** (`config/voices/*.npy`): can be used to clone voices of real people. The framework does NOT verify consent — that's the user's responsibility.
- **Reporting concerns:** if you find a way the system enables non-consensual cloning at scale (e.g., bypassing the warning prompt), report it as a security issue.

### 🧠 Brain adapters
- **API keys** stored in `logica-voice.yaml` or `.env` should never be committed. Our `.gitignore` covers `.env*` by default.
- **LogicaOS bridge**: validates response from `/api/chat/stream` but trusts the brain's tool calls. If you find a way for a malicious response to escalate privileges, report it.

### 💾 Memory
- **pgvector / Chroma**: stored conversation history may contain PII. Apps using Logica Voice should comply with GDPR/LGPD.

## Known limitations (not vulnerabilities)

These are documented design choices, not bugs:

- **WhatsApp via Baileys** runs on a gray-area WhatsApp ToS. Use at your own risk.
- **No end-to-end encryption** between Logica Voice server and channel adapters (they share a process). E2E would require restructuring.
- **Brain adapters trust their endpoints** — a malicious OpenAI-compatible server could inject content. Use trusted providers.

## Security best practices (for users)

1. **Never commit `.env`** — use `.env.example` as template
2. **Use ACL fail-closed** — empty `allowedPhones`/`allowedChatIds` = deny all (default)
3. **Rotate API keys regularly**
4. **Run on isolated user account** — don't give Logica Voice root
5. **Keep dependencies updated** — `pnpm update` periodically
6. **Backup `authDir`** (WhatsApp) — losing it requires re-scanning QR

## License

Reports made under this policy are not subject to additional legal restrictions beyond the MIT license. Reporters retain authorship.
