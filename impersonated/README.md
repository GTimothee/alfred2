# Impersonated Voice Assistant Roadmap

Concise, incremental functionality steps to evolve from a simple local talking bot into an Alexa-like assistant deployed on AWS and accessible via a Raspberry Pi. Each phase should be completed end‑to‑end (working UX + minimal tests + docs) before moving on.

## Phase Progress Overview
Use these master checkboxes to track macro progress (tick only when all sub‑tasks in that phase are complete):

- [ ] Phase 0 – Foundations
- [ ] Phase 1 – Text-To-Speech
- [ ] Phase 2 – Speech-To-Text
- [ ] Phase 3 – Turn & Session Mgmt
- [ ] Phase 4 – Voice & Identity
- [ ] Phase 5 – Memory Layer
- [ ] Phase 6 – Wake Word
- [ ] Phase 7 – Skills Framework
- [ ] Phase 8 – Privacy & Limits
- [ ] Phase 9 – Raspberry Pi Package
- [ ] Phase 10 – AWS Backend
- [ ] Phase 11 – Cloud Sync
- [ ] Phase 12 – Observability
- [ ] Phase 13 – Polishing & UX

## Phase 0 – Foundations
Goal: Minimal text chat loop with a local LLM or remote API.
- [ ] CLI chat: user types, model replies (streaming optional later)
- [ ] Config file: API keys / model selection (`.env`)
- [ ] Basic prompt template + system persona
- [ ] Logging: structured JSON per turn (timestamp, user, assistant, tokens, latency)
- [ ] Simple unit test for chat function
<sub>Acceptance: Run `python chat.py`, send 3 turns, log file contains structured entries, unit test green.</sub>

## Phase 1 – Add Text-To-Speech (Bot Speaks)
Goal: Assistant responds with synthesized voice locally.
- [ ] Integrate TTS engine (ElevenLabs / OpenAI TTS / Coqui / pyttsx3 fallback)
- [ ] Streaming playback while text still generating (if API supports)
- [ ] Audio caching: hash(response_text) -> audio file reuse
- [ ] Configurable voice profile (id, rate, pitch)
- [ ] Robust playback error handling & retry
- [ ] Test: fixed text triggers cached reuse
<sub>Acceptance: Two identical prompts produce only one TTS API call (cache hit second time), playback uninterrupted.</sub>

## Phase 2 – Add Speech-To-Text (Hands-Free Conversation)
Goal: User speaks; assistant transcribes and replies.
- [ ] Microphone capture (simple VAD threshold)
- [ ] STT engine (Whisper local or API) w/ transcript + confidence
- [ ] Push-to-talk OR automatic VAD segmentation
- [ ] Latency metrics (speech start -> transcript -> reply start)
- [ ] Interim transcription display (optional)
- [ ] Tests: mock audio -> expected transcript path
<sub>Acceptance: Speak a 5-word phrase; transcript ≥95% accurate; end-to-end latency under target (e.g., <3s on dev machine).</sub>

## Phase 3 – Turn & Session Management
Goal: Natural multi-turn dialog.
- [ ] Rolling conversation window with token budget trimming
- [ ] Session object (id, started_at, user_profile_ref)
- [ ] Persistence (SQLite / JSONL)
- [ ] /reset command to clear context
- [ ] Safety filters (length, banned phrases) pre-send
- [ ] Metrics: tokens_in/out per session
<sub>Acceptance: Create session, exceed token threshold -> oldest turns trimmed; /reset empties context; metrics exported.</sub>

## Phase 4 – User Voice & Identity Recognition
Goal: Recognize who is speaking (personalization).
- [ ] Voice enrollment (N samples -> embedding)
- [ ] Runtime diarization / verification tagging speaker_id
- [ ] Per-user preferences (name, voice, wake word, reminders)
- [ ] Secure storage (hashed user ids; raw audio discarded unless debug)
- [ ] Consent + delete voice profile command
- [ ] Tests: similarity threshold classification

## Phase 5 – Memory & Knowledge Layer
Goal: Assistant remembers facts over long term.
- [ ] Separate short-term context vs long-term vector store
- [ ] Memory write policy (explicit personal facts only)
- [ ] Retrieval (RAG): inject top-k relevant memories
- [ ] Aging / decay or summarization of stale memories
- [ ] Export + purge tools (data transparency)
- [ ] Tests: retrieval ranking stability

## Phase 6 – Wake Word & Passive Listening
Goal: Hands-free activation.
- [ ] Keyword spotter (Porcupine / Silero / open-wakeword)
- [ ] State machine: idle -> listening -> thinking -> speaking
- [ ] False positive counter + auto sensitivity tuning
- [ ] Visual/audible wake cue (LED or chime)
- [ ] Test harness: replay dataset -> precision / recall

## Phase 7 – Skills & Action Framework
Goal: Extensible capability system.
- [ ] Intent classification (rule-based + LLM fallback)
- [ ] Skill registry (name, triggers, handler)
- [ ] Core skills: time / weather / reminders / Wikipedia
- [ ] Error isolation (fault boundaries per skill)
- [ ] Tracing: log skill latency + outcome
- [ ] Tests: deterministic mocks per handler

## Phase 8 – Privacy, Security & Rate Limits
Goal: Harden before cloud.
- [ ] PII redaction layer before logging
- [ ] API key vault / separation from logs
- [ ] Rate limiting for outbound LLM/TTS/STT calls
- [ ] Graceful degradation messaging
- [ ] Threat model documentation
- [ ] Tests: burst simulation triggers limiter

## Phase 9 – Local Packaging (Raspberry Pi Prototype)
Goal: Run reliably on a Pi.
- [ ] Optimize models (quantized Whisper small, lightweight wake word)
- [ ] systemd service or Docker Compose (auto restart)
- [ ] Hardware abstraction: audio in/out selection
- [ ] LED / GPIO integration (recording & wake indicators)
- [ ] Benchmark: cold start + latency metrics
- [ ] Documentation: Pi setup script & dependencies

## Phase 10 – Cloud Backend (AWS)
Goal: Central coordination & heavier workloads.
- [ ] Core infra: API Gateway, Lambda (skills), DynamoDB (memory/users), S3 (audio cache), CloudWatch
- [ ] Auth: device registration -> JWT issuance
- [ ] Real-time channel (WebSocket or MQTT via IoT Core)
- [ ] Offload heavy summarization / embedding (Lambda or Fargate)
- [ ] IAM least-privilege roles
- [ ] Infra as Code (Terraform / CDK minimal stack)
- [ ] Tests: synthetic conversation pipeline in test stage

## Phase 11 – Device <-> Cloud Sync
Goal: Seamless hybrid operation.
- [ ] Local-first fallback (offline STT/TTS)
- [ ] Delta sync (only new memories / summaries)
- [ ] Heartbeat & health pings
- [ ] Version negotiation (protocol_version)
- [ ] Conflict resolution strategy (timestamp wins + logging)
- [ ] Tests: network flap simulation

## Phase 12 – Monitoring & Observability
Goal: Production readiness.
- [ ] Metrics: latency (p50/p95), skill error rate, wake false positives, token spend
- [ ] Tracing: request id across mic->STT->LLM->TTS pipeline
- [ ] Alerting thresholds (latency, error %, cost anomalies)
- [ ] Memory compaction job metrics
- [ ] Dashboard (Grafana / CloudWatch)

## Phase 13 – Polishing & UX
Goal: Delight.
- [ ] Interruptible TTS (barge-in detection)
- [ ] Adaptive speaking rate (user pace)
- [ ] Persona tuning (style guide + guardrails prompt)
- [ ] Quick responses mode vs detailed mode toggle
- [ ] A/B test greeting variants

## Minimal Initial Milestone Summary
Implement Phases 0–2 only: local text chat + TTS + STT forming a usable voice loop. Defer memory, wake word, skills, and cloud until loop is robust.

### Milestone Success Criteria
- Start to first audible response < 5s typical
- Consecutive identical prompt triggers TTS cache reuse
- STT word accuracy ≥ 90–95% on clear speech sample
- No unhandled exceptions during 10-turn session

## Suggested Directory Structure (Evolving)
voice_assistant/
	core/ (chat loop, config, logging)
	audio/ (input capture, playback, VAD)
	stt/
	tts/
	memory/
	skills/
	wake/
	cloud/
	tests/

## Next Action
Start Phase 0: create a simple `chat.py` with a `ChatSession` class + test.

