# Passingly Informed — Setup & Operations

Everything needed to run, deploy, and wire up your own instance. (For what the project *is*, see README.md.)

---

# Passingly Informed

A tiny daily sports digest for people who don't follow sports but need to make
polite noises about them at the water cooler. It fetches **real** scores and
schedules from ESPN's free JSON, hands them to a small LLM that is only allowed
to *phrase* (never invent), and publishes one short digest a day.

One generation per city per day, shared by everyone who visits. The cost unit is
city-days, not users, so Indy-only is effectively free to run.

- **Live data, never hallucinated.** The model phrases facts it's given. If a fact
  isn't fetched, it can't appear. A made-up score is the one unacceptable failure.
- **Pure standard library.** No `pip install`. Nothing to keep patched.
- **Hosted off your home stack.** GitHub generates and serves it. Your house is
  never in the path.

---

## What's in here

```
passingly_informed.py          the whole brain + site renderer (one file)
.github/workflows/digest.yml    daily cron: generate -> publish to GitHub Pages
README.md                       this file
```

---

## Run it locally first

```bash
export GROQ_API_KEY=...                  # the Groq key you already have
python3 passingly_informed.py            # today's Indianapolis digest
python3 passingly_informed.py --no-llm   # show ONLY the real fetched facts (no Groq)
python3 passingly_informed.py --build ./site   # write site/index.html + site/digest.json
python3 passingly_informed.py --selftest # offline parser check, no network
```

`--no-llm` is your trust check: it prints exactly what was fetched before the
model touches anything. If a team's results don't show, its name in `REGISTRY`
doesn't match ESPN's `displayName` exactly — that's the only field that ever
needs fiddling.

If the Groq call 400s, the model name was probably deprecated. Set
`GROQ_MODEL` to whatever your account lists (`curl https://api.groq.com/openai/v1/models`).

---

## Deploy to GitHub Pages (the main path)

This is the "works from GitHub" setup: a morning Action generates the digest and
publishes it as a static page. No server.

1. **Create a repo** and push these files to it (public is simplest; public repos
   get unlimited Actions minutes).

2. **Add your Groq key as a secret.**
   Repo → Settings → Secrets and variables → Actions → **New repository secret**
   - Name: `GROQ_API_KEY`
   - Value: your key

3. **Turn on Pages.**
   Repo → Settings → Pages → Build and deployment → Source: **GitHub Actions**.

4. **Run it once by hand** to prove it works.
   Repo → Actions → "Daily digest" → **Run workflow**.
   When it's green, your site is live at `https://<username>.github.io/<repo>/`.
   After that it runs itself every morning (11:30 UTC — see the DST note in the
   workflow file).

Optional repo settings the page will pick up if present (all safe to skip):
- **Variables** (Settings → Variables): `TIP_URL`, `SOURCE_URL`, `GROQ_MODEL`
- **Secrets**: `FORM_ENDPOINT` (the email signup endpoint — see Email below)

Without `TIP_URL` the tip line is hidden. Email stays completely off until you
choose to turn it on (see Email below) — no form, and not even a "coming soon"
note, so nothing about an unbuilt list is ever advertised.

---

## Point your Cloudflare domain at it

Use a subdomain — it's the least fussy. Say `sports.yourdomain.com`:

1. **Cloudflare → DNS → Add record**
   - Type: `CNAME`
   - Name: `sports`
   - Target: `<username>.github.io`
   - Proxy status: **DNS only (grey cloud)** to start. This lets GitHub validate
     the domain and issue its own HTTPS cert without a redirect loop. Once the
     cert is live you *can* flip the proxy on (orange cloud) with SSL/TLS mode set
     to **Full** if you want Cloudflare in front — but grey-cloud is fine forever.

2. **GitHub → Settings → Pages → Custom domain**: enter `sports.yourdomain.com`,
   save. Wait for the cert to provision (a few minutes), then tick **Enforce HTTPS**.

(Apex `yourdomain.com` works too, but needs four `A` records to GitHub's Pages IPs
instead of a CNAME. The subdomain is less hassle.)

---

## Home Assistant: "Hey Nabu, what's the sports news?"

The build writes `digest.json` next to the page, and it includes a `speech` field
that's pre-cleaned for text-to-speech (no asterisks, natural sentences). HA reads
that.

**1. A sensor that pulls the digest once an hour** — add to `configuration.yaml`:

```yaml
rest:
  - resource: "https://sports.yourdomain.com/digest.json"
    scan_interval: 3600
    sensor:
      - name: "Passingly Informed"
        unique_id: passingly_informed
        value_template: "{{ value_json.date }}"
        json_attributes:
          - city
          - display
          - speech
          - generated_at
```

The spoken digest now lives at
`state_attr('sensor.passingly_informed', 'speech')`.

**2. A voice command that reads it** — add an automation (UI → Automations → edit
in YAML, or `automations.yaml`):

```yaml
- alias: "Sports digest (voice)"
  triggers:
    - trigger: conversation
      command:
        - "what's the sports news"
        - "what is the sports news"
        - "what's the sports digest"
        - "what can I talk about for sports"
        - "give me the sports digest"
  actions:
    - set_conversation_response: >-
        {{ state_attr('sensor.passingly_informed', 'speech')
           or "I couldn't reach the sports digest just now." }}
  mode: single
```

Now any Assist satellite — Voice PE, your VACA/Net-chan kitchen display, the phone
app — answers those phrases by speaking the day's digest through whatever pipeline
heard you. Reload automations (or restart) and try it.

(If you'd rather have Net-chan say it in her own voice/personality, point the
automation at her TTS service with the same `speech` attribute as the message
instead of using `set_conversation_response`.)

---

## Email signups (the honest version)

Email is **off by default** — no form renders, and `EMAIL_TEASER` is `False`, so
the page makes no promise about a list you haven't built yet. When you're ready,
set `FORM_ENDPOINT` to a real endpoint and the signup form appears (or flip
`EMAIL_TEASER` to `True` first if you just want a "coming soon" note while you
build).

**The hard part of email is *sending*, not collecting** — getting mail into
strangers' inboxes means SPF/DKIM/DMARC, IP reputation, and constant spam-folder
babysitting. Don't self-host SMTP for this. Outsource the sending and it gets
easy. Two no-server routes:

- **Buttondown** (a newsletter service, free tier). Point `FORM_ENDPOINT` at its
  embed endpoint (or just link its hosted subscribe page from the footer).
  Buttondown stores the list and handles delivery; the GitHub Action calls its API
  once a day to send the digest as a broadcast. Least code.
- **Cloudflare Worker + Resend** (you already live in Cloudflare). A Worker catches
  the form POST and stashes the address in Cloudflare KV/D1; the Action (or a
  scheduled Worker) sends via Resend's API. More control, still serverless, still
  off your home stack, still free-tier.

Either way: no VPS required for email. When you pick one, wiring the form +
the send step into the Action is a small, self-contained job.

---

## Pushing to non-technical people (e.g. your dad)

There's no free, no-app, scheduled push channel that beats email for a normal
person — and that's worth saying plainly rather than pretending otherwise:

- **Email** is the easiest *receiving* experience there is. Your dad already has
  it, nothing to install, it just arrives. The only "hard" was sending, and the
  section above outsources that. This is the answer for non-technical folks.
- **RSS** (easy to add to the build later) is great for the nerdy users and is a
  clean Home Assistant input — but your dad won't use it.
- **Zero-setup fallback:** the digest is just a URL on your domain. Dad can
  bookmark it or "Add to Home Screen" and tap it like an app. No push, but no
  signup either.
- **SMS** is universal and no-app, but it costs per message and now requires
  carrier A2P registration — not worth it at this scale.
- **Telegram/chat broadcasts** are free but require installing the app.

Short version: **email for the normies (via a managed sender), the page + RSS for
the nerds and Home Assistant.**

---

## Moving to a VPS later — yes, and it's reversible

Starting on GitHub locks you into nothing. **Your domain is the stable anchor**,
and it lives at Cloudflare, not at GitHub.

The day you want a $22/yr box instead:

1. Run `passingly_informed.py --build /var/www/site` from cron on the VPS (same
   script, same output).
2. Serve that folder with any static web server (Caddy, nginx, `python3 -m
   http.server` — it's static files).
3. In Cloudflare, change the DNS record from the GitHub CNAME to the VPS's IP.

That's it. The brain doesn't change, the page doesn't change, and anyone who
bookmarked the domain notices nothing. You can even keep generating on GitHub and
only move the serving, or move the whole thing — both fine. No re-architecting,
no lock-in.

---

## Adding cities later

`REGISTRY` in `passingly_informed.py` is plain data. Copy the Indianapolis block,
change the label, set each team's `name` to ESPN's exact `displayName`, add any
marquee `events` and evergreen `context`. Run `--no-llm <city>` to confirm the
feeds resolve before turning the model loose.

Per-city generation is per-city cost, so this is also the natural seam for a paid
"follow your own out-of-town teams" tier down the road: the shared local digest
stays free, personal teams fund their own tokens.
```
