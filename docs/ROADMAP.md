# ROADMAP — Logica Voice

## v0.1 — MVP local (4 semanas)

**Meta:** rodar no Mac mini do Arquiteto, substituindo `channels/whatsapp/bot.js` + `channels/telegram/bot.js` + ElevenLabs no Voice.

### Semana 1 — Foundation
- [ ] Setup TS project com workspace (`packages/core`, `packages/adapters`, `packages/cli`)
- [ ] `adapters/base.ts` — interface `ChannelAdapter`, `ChannelMessage`, `AgentResponse`
- [ ] `bridge.ts` — chama `chat-loop.js` do brain LogicaOS
- [ ] Identity resolver multi-canal
- [ ] ACL unificado (yaml + env)

### Semana 2 — Canais texto
- [ ] WhatsApp adapter: refatora `channels/whatsapp/bot.js` (preserva LID fix, anti-flood)
- [ ] Telegram adapter: refatora `channels/telegram/bot.js`
- [ ] Notifier dedup integrado (já existe)
- [ ] Smoke test: msg WhatsApp → brain → resposta correta

### Semana 3 — Voice via Pipecat
- [ ] Pipecat embedded (subprocess Python ou WebSocket)
- [ ] STT faster-whisper MLX local
- [ ] TTS Kokoro-82M local (default), F5-TTS opcional (qualidade)
- [ ] Logica Voice desktop conecta via WebSocket
- [ ] Push-to-talk funcionando

### Semana 4 — Polish + docs
- [ ] CLI básico: `logica start|stop|status|logs`
- [ ] README completo dentro do próprio repo (sem site)
- [ ] Migração: deprecar `channels/{whatsapp,telegram}/` originais
- [ ] PM2 config único

**Critério de release v0.1:**
- ✅ 3 canais funcionando paralelos com mesma memória
- ✅ Brain LogicaOS responde nos 3 sem mudança
- ✅ ElevenLabs removido (Kokoro+F5 substitui)
- ✅ Zero custo cloud TTS/STT

---

## v0.2 — Modo Jarvis (2 semanas)

**Meta:** conversação contínua estilo Iron Man/Gemini Live.

- [ ] Moshi MLX rodando local (pip install moshi_mlx)
- [ ] Wake word "Astro" / "Hey Logica" (Picovoice ou modelo custom Moshi)
- [ ] Switcher modo padrão ↔ modo Jarvis via comando/botão
- [ ] Barge-in nativo (Moshi suporta)
- [ ] Streaming bidirecional Logica Voice ↔ Moshi
- [ ] Fallback automático Moshi → Pipecat se Moshi crashar

**Critério v0.2:**
- ✅ "Astro, qual a hora?" responde em <500ms sem botão
- ✅ Interromper durante fala do Astro funciona
- ✅ Conversa fluida sem turnos rígidos

---

## v0.3 — Voice Cloning (1 semana)

**Meta:** cada agente tem sua própria voz, treinada com áudio do usuário ou referência.

- [ ] Wizard: usuário grava 10-15s, gera embedding F5-TTS
- [ ] Por agente: associa embedding ao slug (Astro=voz1, Luna=voz2)
- [ ] Storage local (`config/voices/<slug>.npy`)
- [ ] UI no dashboard pra ouvir/regravar

---

## v0.4 — Open Source Release (2 semanas)

**Meta:** virar projeto público que qualquer dev pode instalar.

- [ ] Licença MIT no repo
- [ ] CONTRIBUTING.md + Code of Conduct
- [ ] Docker compose minimal
- [ ] `npx logica-voice init` standalone (não requer LogicaOS completo)
- [ ] 3 templates: assistente pessoal, suporte cliente, vendas
- [ ] GitHub repo público: `github.com/Rovemark/logica-voice`
- [ ] ~~Landing page~~ (descartado — só repo GitHub é suficiente)
- [ ] Anúncio: HN, Reddit r/LocalLLaMA, Discord LangChain

**Critério v0.4 (release público):**
- ✅ Stranger consegue rodar `npx ...` e ter bot WhatsApp + Voice em 10min
- ✅ README claro com benchmarks vs ElevenLabs (custo)
- ✅ Issues template + bug report flow
- ✅ Pelo menos 1 cliente externo (não Andre/Lou/Mario) rodando

---

## v0.5 — Mobile + Web (3 semanas)

**Meta:** Logica Voice como PWA mobile + WebRTC nativo no dashboard.

- [ ] WebRTC client no dashboard React (substitui WebSocket simples)
- [ ] PWA mobile (iOS/Android via web)
- [ ] LiveKit integração opcional (cloud WebRTC pra usuários sem servidor local)
- [ ] Multi-room (conversa em grupo via WhatsApp/Telegram)

---

## v1.0 — Production hardening (4 semanas)

**Meta:** rodar em escala (10+ clientes simultâneos).

- [ ] Load testing
- [ ] Graceful degradation (Moshi cai → Pipecat assume)
- [ ] Multi-tenant (cada licença LogicaOS = workspace isolado)
- [ ] Métricas Prometheus
- [ ] Sentry-like error tracking (self-hosted)
- [ ] Backup/restore conversation history
- [ ] Migrations versionadas

---

## Backlog (sem prazo, lista de ideias)

- [ ] Discord adapter
- [ ] Slack adapter
- [ ] iMessage adapter (macOS only)
- [ ] Email adapter (recebe via IMAP, responde via SMTP)
- [ ] SMS via Twilio adapter (opcional cloud)
- [ ] Vídeo: agente vê webcam (Gemini-style multi-modal)
- [ ] Avatar 3D talkativo (D-ID open-source equivalent)
- [ ] Tradução em tempo real entre idiomas (PT-BR ↔ EN ↔ ES)
- [ ] Modo bilíngue: Astro fala PT, user fala EN, ambos entendem
- [ ] Plugins comunidade (npm/pypi packages)
- [ ] Integration tests com 5 canais simultâneos
- [ ] Editor visual de chains (no-code, tipo n8n) embedded
