# Contributing to Logica Voice

Thanks for your interest! Logica Voice is MIT, no CLA, no strings — we want your contributions.

## Quick start

```bash
# Fork on GitHub, then:
git clone https://github.com/YOUR_USERNAME/logica-voice.git
cd logica-voice
pnpm install
pnpm -r build
pnpm -r typecheck
```

## How to contribute

### 🐛 Found a bug?
Open an [issue using the Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md). Include:
- Logica Voice version
- Node version (`node --version`)
- OS (`uname -a` or Windows version)
- Channel/brain config (with secrets redacted)
- Steps to reproduce

### ✨ Have an idea?
Open a [Feature Request issue](.github/ISSUE_TEMPLATE/feature_request.md) first to discuss before coding.

### 📝 Improving docs?
Just open a PR. Docs PRs don't need prior discussion.

### 💻 Writing code?

1. **Pick an issue** labeled `good first issue` or `help wanted` (or open a new one)
2. **Discuss the approach** in the issue if non-trivial
3. **Fork + branch:** `git checkout -b feat/short-description`
4. **Code + test:** keep changes focused (one feature/fix per PR)
5. **Run checks:** `pnpm -r typecheck && pnpm -r build`
6. **Commit:** use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `chore:`, etc.)
7. **PR:** fill the [template](.github/PULL_REQUEST_TEMPLATE.md), link the issue

## Project structure

```
packages/
├── core/                   # frames, pipeline, adapter interfaces
├── brain/                  # LLM adapters (built-in, logicaos, openai, ...)
├── adapters/               # channel adapters (telegram, whatsapp, voice, web)
├── voice/                  # STT/TTS/Moshi services
└── cli/                    # logica-voice command
```

Each package has its own `package.json`, `tsconfig.json`, and `src/`. They link via pnpm workspaces (`workspace:*` deps).

## Coding guidelines

- **TypeScript strict mode** — no `any` unless absolutely necessary (use `unknown` + type guards)
- **2 spaces** indentation, **single quotes**, semicolons
- **No dependencies in `core`** — keep it zero-dep
- **Async iterators** for streaming (not RxJS in hot paths)
- **Document non-obvious code** with JSDoc
- **One concept per file** — small, focused modules

## Adding a new adapter

### Channel adapter
1. Create `packages/adapters/<name>/`
2. Implement `ChannelAdapter` interface from `@logica-voice/core`
3. Extend `BaseChannelAdapter` for shared boilerplate
4. Add `package.json` + `tsconfig.json` following existing pattern
5. Update `packages/cli/src/index.ts` to load it
6. Add docs in `docs/CHANNELS.md`
7. Add example in `examples/`

### Brain adapter
1. Create `packages/brain/<name>/`
2. Implement `BrainAdapter` interface
3. Stream `BrainChunk`s via `chat()` async generator
4. Same package layout
5. Update `packages/cli/src/index.ts` loader
6. Document in `docs/BRAIN-ADAPTERS.md`

### Voice service
1. Create `packages/voice/<name>/`
2. Implement `VoiceService` interface
3. If using Python (subprocess), include scripts in `scripts/`
4. Document Python deps in package README

## Testing

We're still setting up the test infrastructure. For v0.1, manual testing via the smoke script:

```bash
pnpm -r build
node packages/cli/bin/logica-voice.js init /tmp/test-bot
cd /tmp/test-bot
# edit logica-voice.yaml
node /path/to/logica-voice/packages/cli/bin/logica-voice.js start
```

Vitest test suite coming in v0.2.

## Commit message style

```
feat(adapter-telegram): add inline keyboard support
fix(brain-built-in): handle empty SSE chunks
docs(stack): update Moshi version requirements
chore(deps): bump baileys to 6.18
refactor(core): split pipeline into smaller files
```

Use `BREAKING CHANGE:` in commit body for breaking changes.

## Release process

Currently manual (will automate with Changesets in v0.2):

1. Update `CHANGELOG.md`
2. Bump `version` in `packages/*/package.json`
3. `git tag v0.X.Y -m "release notes"`
4. `git push --tags`
5. `gh release create v0.X.Y --notes-from-tag`

## Questions?

- **Bug/feature:** GitHub Issues
- **Design discussion:** GitHub Discussions (coming soon) or an issue with `discussion` label
- **Security:** see [SECURITY.md](SECURITY.md)

## License

By contributing, you agree your contributions are MIT licensed (same as the project). No CLA required.

---

Thanks for making Logica Voice better! 🙏
