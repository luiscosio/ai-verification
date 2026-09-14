# Hosted proof workspace on AgentMetal

This is a password-protected, single-workspace deployment. Everyone with the login shares one active job and its latest prompt/result. It is not a public multi-user prover. GitHub Pages remains the public browser verifier. Neither deployment changes proof coverage.

The prover listens only on loopback inside the Caddy network namespace. Caddy provides HTTPS and authenticates every page and API request; no Python port is published. The application independently checks the configured Host/Origin and its per-process request token. Prompts execute on this server, as the hosted UI states. Private temporary traces are removed by the existing job cleanup; the latest prompt/result stays in memory until replacement or restart.

## Provision and deploy

1. Mint a single-use AgentMetal coupon through the authenticated `POST /admin/coupons` endpoint, limited to `medium`, seven days, 100% discount and one-day redemption expiry. Keep the code private.
2. Redeem it through `POST /v1/servers`, supplying the public half of a dedicated SSH key, `plan: medium`, `days: 7`, and `os: ubuntu-24.04`. Save the returned server ID and lease expiry. If provisioning is uncertain, inspect the coupon's `usedBy` before retrying; never blindly mint another coupon.
3. On the assigned server, install Docker Engine and Compose, configure a hostname resolving to its address, and open only web ports 80/443 through AgentMetal's firewall API from that server. Keep SSH key-only.
4. Copy this directory to the server. Create a private `.env` file alongside it, containing `APP_REVISION` (the full reviewed public repository commit), `PROVER_DOMAIN`, and `PROVER_PASSWORD_HASH` (bcrypt). Use `caddy hash-password` to generate the hash; keep the plaintext password outside Git. Quote the hash in the environment file so its dollar signs remain literal.
5. Run `docker compose --env-file .env config --quiet`, then `docker compose --env-file .env up -d --build`. The image fetches exactly the selected commit and pinned submodule, installs the authenticated model/materials, builds the CPU executable and page, and runs as an unprivileged user.
6. Verify HTTPS, unauthenticated rejection, authenticated generation, proof download and independent verification. Reject changed sums, wrong origins and missing request tokens. Confirm that port 8789 is unreachable externally. Record the deployed commit, server ID and expiry; renew explicitly before expiry if the service should continue.

The 8 GB plan accommodates the measured approximately 6.22 GiB peak summed runner RSS with one job at a time. Container memory is capped at 7 GiB. Temporary traces use a disk volume, not a memory-backed filesystem; a roughly 1.5 GiB trace must not consume additional RAM through tmpfs. Actual performance and memory still need validation on the target host.

## September 13 provisioning attempt

A limited coupon was minted. Two redemption attempts returned HTTP 502; the API log reported **server limit reached** for both Ashburn and Hillsboro. The coupon was confirmed unused, and the backing project listed five running servers. No existing server was deleted or repurposed. Deployment requires a higher project server limit or an explicitly selected existing host. The container deployment has not yet been exercised on a target server.

Coupon, SSH key and request records are kept outside tracked files under `.receipts-cache/agentmetal-20260913/` in the operator checkout. The coupon expires after one day if not redeemed. Do not copy the AgentMetal monorepo, its admin token or its infrastructure credentials into this public repository or the prover image.
