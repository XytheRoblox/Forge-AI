# Forge — 10-minute demo, shot list & voiceover

Recorded and edited, aimed at judges. The through-line:

> Most agent builders are a prompt box with a logo. Forge compiles an agent into its own
> running container — its own URL, its own tools, its own memory.

Every shot exists to make that concrete rather than claimed.

---

## Because it's edited, not live

- **Record screen and voice separately.** Clean silent screen passes, then read the voiceover
  against the footage. You stop fumbling narration while typing, and you retime the VO to fit
  the visuals instead of the reverse.
- **Cut every wait.** The deploy takes minutes; give it six seconds. Hold on the first two
  steps, jump cut, land on all eight green. Dead air is what makes ten minutes feel like twenty.
- **Shoot out of order.** The memory and tool-log shots need an agent that's already been used —
  record them last, cut them in at 7:15.
- **Zoom and annotate in post.** Terminal output and `CACHE.md` are small text. Record at ~140%,
  then push in on the exact line that matters.

## Set up before the first pass

- [ ] **Record on Qwen or DeepSeek — not Llama.** Meta's `meta-llama/*` builds are frequently
      capacity-exhausted on Featherless. Of all 14 catalog models, 13 were ready and both
      failures were Llama.
- [ ] **Don't switch models rapidly between takes** — the plan allows four switches per minute.
- [ ] **Pre-warm images with a throwaway build.** A cold build compiles images.
- [ ] **Have a screenshot ready** for the vision shot — legible text and an obvious badge.
- [ ] Docker Desktop up, backend on `:8000`, frontend on `:5173`, header reads **Docker up**.
- [ ] Terminal beside the browser with `docker ps` ready. This is your proof shot.
- [ ] Hide bookmarks, notifications, second-monitor clutter.

---

## The rundown

### 0:00 · 0:40 — Cold open, state the claim

> "Every AI agent builder I've used is a text box that saves a prompt. Forge is a compiler. You
> describe an agent, and it produces a running container — its own web address, its own tools,
> its own memory. Here are three agents I built earlier, running right now."

- SHOW `docker ps` — agent containers plus shared capability containers
- SHOW the dashboard with the **Docker up** badge

Falsifiable claim, immediate evidence. Containers on screen in the first 40 seconds separates
you from every prompt wrapper.

### 0:40 · 1:50 — Build one live

> "I'll build a math tutor. I pick a model — grouped by who made the weights, Llama, DeepSeek,
> Mistral, Qwen — then attach capabilities. Then the part I like most: I don't write a system
> prompt, I write one sentence about what it's for."

- CLICK New Agent → name → open the **Qwen** family
- CLICK attach **WolframAlpha**
- TYPE "A patient high-school math tutor who explains step by step."
- SHOW the expanded system prompt appearing

Say the quiet part: manifesto expansion runs on the platform's key, not the user's.

### 2:30 · 1:00 — Deploy, the eight-step pipeline

> "Deploying isn't saving a config. It validates, writes the agent's files, starts the capability
> servers it needs, generates its webpage, builds the container, health-checks it, then sends it a
> test message and calls its endpoints. If any step fails, the agent doesn't ship."

- SHOW steps turning green
- CUT hold on first two → jump cut → land on all eight
- POST freeze and highlight "Test chat"

The last two steps mean a deployed agent has provably already answered a message.

### 3:30 · 1:00 — It's real, and it dressed itself

> "There's the container. This is its own page, on its own port — I can send this URL to anyone.
> I never picked these colours: a model read the agent's purpose and designed the theme. A math
> tutor gets chalkboard green, graph paper, and a monospace face."

- SHOW `docker ps` → the new `zovo-agent-N`
- SHOW the themed page; let it sit

The engineering point, in one sentence: the model never emits markup or CSS. It returns a
constrained spec — colours, one of five patterns, one of four type stacks — validated field by
field. So the page can look like anything and the chat can't break.

### 4:30 · 1:30 — Real tools, in separate containers

> "Ask it something it can't do alone. It calls WolframAlpha — its own container, spoken to over
> MCP, shared across every agent that needs it."

- TYPE "Compute the definite integral of x² from 0 to 7."
- SHOW the status line naming the tool live: *Thinking… → Contacting wolfram alpha…*
- SHOW `docker ps` → `forge-mcp-wolfram_alpha` as its own process

Optional flex: Firecrawl is wired the same way — "scrape example.com and tell me the heading."

### 6:00 · 1:15 — Best beat: vision on a model that can't see

> "This agent runs on a text-only model. It has no vision. Watch." *(upload)* "It just read the
> interface. When a model can't take images, Forge routes the upload to a vision model and hands
> the agent the description. Image support became a property of the platform instead of a property
> of the model you picked."

- SAY the model name **before** uploading — the setup is the trick
- POST superimpose the model id during the setup line
- Leave a beat of silence after the answer lands

Setup, turn, payoff in 90 seconds. Don't cut this for time.

### 7:15 · 1:30 — Memory, and working memory

> "Tell it something. It decides to save it — that's a tool call, not a transcript. Now a
> completely new conversation, no history at all… and it still knows. Separately it keeps a log of
> the tool calls it made and what they returned, so a multi-step problem builds on the last step
> instead of recomputing it."

- TYPE "My name is Ishaan and my calculus exam is on the 14th."
- SHOW `CACHE.md` — memory entry and tool call log side by side
- Fresh chat → "What do you know about me?"
- TYPE "What was the last integral, and what was it? Multiply it by 3."

Memory is long-term; the tool log is working memory. Showing the plain markdown file is the
credibility move — inspectable, not a black box.

### 8:45 · 1:15 — Close on rigour

> "One last thing. Capabilities only work if the model can genuinely call tools — so every model
> in this list was tested against the live API with a real multi-step tool loop, and the ones that
> only *look* like they're calling a tool aren't in the list. Several popular models print the JSON
> as prose and never call anything. An agent built on those would look fine and silently do nothing."

- SHOW the model picker — "everything here is verified"
- SAY one line on what's next

Anyone can add models to a dropdown. Testing them all and deleting the ones that don't work is a
judgment call about quality.

---

## In the edit

- **Burn in captions.** Judges watch muted or at speed, and auto-captions mangle MCP,
  WolframAlpha, sidecar.
- **Callout the one line that matters** in every terminal shot — otherwise the proof shot reads
  as set dressing.
- **Quiet chapter title** on each of the eight shots.
- **Cold open on the payoff**, then title card, then the real opening.

## Don't claim these

- **Scheduled jobs.** Cron config validates; a scheduled run has never been observed firing.
- **GitHub, filesystem, browser automation.** Images build; containers never started. Demo
  WolframAlpha, Firecrawl and Time — those are proven end to end.
- **Cloud deployment.** The Cloud Run path is entirely untested. Say "designed for", not "supports".
- **"Any model works."** Say "any verified model" — one catalog model calls tools correctly and
  then ignores what comes back.

## Pocket answers

**"Isn't this just a wrapper around an API?"** No — the output is a container. Each agent is an
independently deployable service with its own HTTP endpoints and web UI. You can curl an agent's
custom endpoint without ever opening Forge.

**"Why containers instead of just calling the model?"** Isolation and portability. Each agent
carries its own workspace, memory and capability wiring. It's also what makes per-agent tools
tractable — capabilities are separate processes shared across agents, not duplicated per agent.

**"How do you know the tools actually run?"** The deploy pipeline sends a test message and
exercises every custom endpoint before marking an agent deployed, and a capability that starts and
dies is caught rather than reported healthy. One wired capability was silently crash-looping until
that check existed.

**"What was the hardest problem?"** Making image support independent of the model. The obvious
approach restricts image agents to vision models; instead uploads route through a vision sidecar
so every agent can see. Second: discovering that "returns a tool call" and "completes a tool loop"
are different things, and some models do the first but not the second.
