# Capability logos

Drop a brand mark here named after its capability key, and the agent chat page
will use it in place of that capability's emoji on the "Used" chips under each
reply.

    wolfram_alpha.svg      -> WolframAlpha
    firecrawl.svg          -> Web Search & Scrape
    time.svg               -> Time
    github.svg             -> GitHub
    remember.svg           -> the built-in Memory tool

`.svg` is preferred; `.png` also works. Anything else is ignored.

The file is base64-inlined into each agent's generated page at build time — the
agent container serves one self-contained HTML file and has no static asset
route, so the bytes have to travel inside the page. Keep marks small (a few KB)
and square-ish; they render at 14px.

A capability with no file here silently falls back to the emoji in
`registry.py`, so this directory can be empty or partial.
