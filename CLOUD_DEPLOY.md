# ProposalAI Cloud Deployment

Use a small Ubuntu VPS with a fixed public IPv4. This is better than laptop scheduling or dynamic serverless jobs because Brevo is enforcing authorised IP addresses.

## Recommended Server

- Ubuntu 24.04 LTS
- 1 vCPU / 1 GB RAM is enough
- Fixed public IPv4
- Providers: Hetzner, DigitalOcean, Vultr, Linode, AWS Lightsail

## 1. Prepare The Server

SSH into the server, then run:

```bash
sudo apt-get update
sudo apt-get install -y git
```

Copy this project to `/opt/ProposalAI`. If the GitHub repo is available:

```bash
sudo mkdir -p /opt
sudo chown "$USER":"$USER" /opt
git clone YOUR_GITHUB_REPO_URL /opt/ProposalAI
cd /opt/ProposalAI
```

If you are copying from the laptop instead:

```powershell
scp -r "C:\Users\ksoub\OneDrive\Desktop\New folder\All Data\Personal\Project\ProposalAI" root@SERVER_IP:/opt/ProposalAI
```

Then install Docker:

```bash
cd /opt/ProposalAI
bash cloud/bootstrap_ubuntu.sh
```

Log out and back in if Docker asks for sudo.

## 2. Add Secrets On The Server

Do not commit `.env`. Create it directly on the VPS:

```bash
cd /opt/ProposalAI
cp cloud/.env.cloud.example .env
nano .env
```

Set the same Brevo, Hunter, reply email, address, and report email values.

If you want to migrate the laptop data:

```powershell
scp -r "C:\Users\ksoub\OneDrive\Desktop\New folder\All Data\Personal\Project\ProposalAI\revenue_ops_data" root@SERVER_IP:/opt/ProposalAI/revenue_ops_data
```

## 3. Authorise The VPS IP In Brevo

On the VPS:

```bash
curl -4 https://ifconfig.me
```

Copy that IPv4 address into Brevo:

```text
Brevo dashboard -> Security -> Authorised IPs -> Add IP
```

This step is required. Without it, Brevo returns `401 Unauthorized` or `Unauthorized IP address`.

## 4. Start ProposalAI Revenue Ops

```bash
cd /opt/ProposalAI
docker compose up -d --build
docker compose ps
```

Services:

- `scheduler`: runs lead finder, outreach, retries, follow-ups, reply checks, summaries
- `webhook`: receives Brevo inbound/event webhooks on port `8770`
- `dashboard`: local dashboard on server port `8765`, bound to localhost only

## 5. Test Sending

```bash
docker compose exec scheduler python -m revenue_ops send-summary
```

If this works, the 8 PM summary will work from the VPS.

## 6. View Dashboard

The dashboard is intentionally not public. Use an SSH tunnel:

```bash
ssh -L 8765:127.0.0.1:8765 root@SERVER_IP
```

Then open:

```text
http://127.0.0.1:8765
```

## 7. Configure Brevo Webhooks

If Brevo accepts HTTP webhooks:

```text
http://SERVER_IP:8770/brevo/events?secret=YOUR_BREVO_WEBHOOK_SECRET
http://SERVER_IP:8770/brevo/inbound?secret=YOUR_BREVO_WEBHOOK_SECRET
```

If Brevo requires HTTPS, point a domain/subdomain to the VPS and use Caddy or another reverse proxy. See `cloud/Caddyfile.example`.

## Useful Commands

```bash
docker compose logs -f scheduler
docker compose logs -f webhook
docker compose restart scheduler
docker compose exec scheduler python -m revenue_ops email-pipeline --queue-only
docker compose exec scheduler python -m revenue_ops send-emails
docker compose exec scheduler python -m revenue_ops check-replies
docker compose exec scheduler python -m revenue_ops send-summary
```

## Cloud Schedule

All times are IST:

- After 9:00 AM: lead finder + queue + sender
- After 10:00 AM: follow-ups
- Business hours: reply checks and hourly retry
- After 8:00 PM: daily summary
- After 8:30 PM: backup summary if the first one failed
