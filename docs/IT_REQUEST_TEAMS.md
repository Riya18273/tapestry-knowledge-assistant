# IT Request — enable "Ask Tapestry" in Microsoft Teams

**What this is:** an internal Q&A assistant over our Tapestry Confluence content. It already
runs as a Docker service (web chat works on the LAN). To add a **Teams chatbot**, Microsoft's
Teams cloud must be able to reach one API endpoint over **public HTTPS**. Everything else is done.

## The single ask
Give this endpoint a **public HTTPS URL**, forwarding to the internal service:

```
https://ask-tapestry.<company>.com/api/v1/teams   →   http://10.30.156.124:8000/api/v1/teams
```

- Publish **only** the path `/api/v1/teams`. Keep everything else (`/`, `/docs`, `/api/v1/ingest`)
  **internal-only**.
- The endpoint is **HMAC-verified** (rejects any request not signed by our Teams webhook token),
  so exposing just this path is safe.

## Any ONE of these works
| Option | What IT does | Cost |
|---|---|---|
| **A. Corporate reverse proxy / API gateway (preferred)** | Add a rule: public `…/api/v1/teams` → `10.30.156.124:8000`. Ready-made nginx/Caddy configs in `docs/DEPLOYMENT.md` §7b. | ~$0 (existing gateway + TLS) |
| **B. DNS + NAT + TLS on the server** | Public DNS name → NAT to `10.30.156.124`, reverse proxy + Let's Encrypt TLS | ~USD 10–15/yr domain; TLS free |
| **C. Host in Azure** | Run the same Docker stack on an Azure VM/Container (public HTTPS) | small Azure compute; still $0 Claude |

## Prerequisites for A/B
- A **public DNS name** (e.g. `ask-tapestry.<company>.com`) → the proxy's public IP
- **Inbound 443** open to the proxy; proxy able to reach `10.30.156.124:8000` internally
- A **TLS certificate** (Let's Encrypt = free)

## After the URL exists (2 minutes, done by a team owner)
1. Teams → target team → ••• → **Manage team → Apps → Create an outgoing webhook**.
2. **Callback URL** = `https://ask-tapestry.<company>.com/api/v1/teams`.
3. Copy the **security token** it shows → set `TAPESTRY_TEAMS_SECRET` in the server's `.env` → restart the `api` container.
4. In the team: `@AskTapestry what changed in release 1.0.1?`

## Cost
**$0** Microsoft/bot licensing, **$0** AI (runs on local Ollama). Only marginal cost is a
domain (~USD 10–15/yr) if not using an existing gateway.

_Config details (reverse-proxy rules, Docker, env) are in `docs/DEPLOYMENT.md` (§Internal-only
deployment and §7b)._
