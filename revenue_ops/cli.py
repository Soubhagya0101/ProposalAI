from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import RevenueOpsConfig
from .email_campaign import EmailCampaign
from .lead_finder import LeadFinder
from .models import Lead
from .workflow import RevenueAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ProposalAI revenue automation")
    parser.add_argument("--data-dir", default=None, help="Local fallback data directory")
    subcommands = parser.add_subparsers(dest="command")

    subcommands.add_parser("init", help="Create local CSV storage files")

    add_lead = subcommands.add_parser("add-lead", help="Add or update a lead")
    add_lead.add_argument("--name", default="")
    add_lead.add_argument("--company", default="")
    add_lead.add_argument("--email", default="")
    add_lead.add_argument("--profile-url", default="")
    add_lead.add_argument("--niche", default="")
    add_lead.add_argument("--country", default="")
    add_lead.add_argument("--review-count", type=int, default=0)
    add_lead.add_argument("--source", default="manual")
    add_lead.add_argument("--need", default="")
    add_lead.add_argument("--budget", default="")
    add_lead.add_argument("--notes", default="")
    add_lead.add_argument("--score", type=int, default=0)

    outreach = subcommands.add_parser("draft-outreach", help="Create a safe under-100-word outreach draft")
    outreach.add_argument("lead_id")

    contact = subcommands.add_parser("record-contact", help="Record a manual contact and schedule follow-up")
    contact.add_argument("lead_id")
    contact.add_argument("--message-id", default=None)

    event = subcommands.add_parser("record-event", help="Record a lead event such as reply or meeting_booked")
    event.add_argument("lead_id")
    event.add_argument("kind")
    event.add_argument("--detail", default="")

    feedback = subcommands.add_parser("record-feedback", help="Record message feedback and flag strong responses hot")
    feedback.add_argument("lead_id")
    feedback.add_argument("message_id")
    feedback.add_argument("--rating", type=int, required=True)
    feedback.add_argument("--sounded-like-you", default="")
    feedback.add_argument("--make-better", default="")
    feedback.add_argument("--would-pay-9", default="")
    feedback.add_argument("--notes", default="")

    import_csv = subcommands.add_parser("import-csv", help="Import allowed lead exports; keeps only leads with fewer than 10 reviews")
    import_csv.add_argument("path")

    dashboard = subcommands.add_parser("dashboard", help="Run the live local dashboard")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", default=8765, type=int)

    subcommands.add_parser("find-leads", help="Run Hunter, Reddit, and configured CSV lead finding")
    subcommands.add_parser("queue-emails", help="Queue personalized cold emails for new leads")

    send_emails = subcommands.add_parser("send-emails", help="Send queued emails through Brevo SMTP")
    send_emails.add_argument("--max", type=int, default=None)
    send_emails.add_argument("--dry-run", action="store_true")
    send_emails.add_argument("--no-delay", action="store_true")

    subcommands.add_parser("check-replies", help="Scan optional IMAP inbox or report Brevo webhook mode")
    brevo_webhook = subcommands.add_parser("process-brevo-webhook", help="Process a saved Brevo webhook JSON payload")
    brevo_webhook.add_argument("path")
    brevo_webhook.add_argument("--kind", choices=["auto", "event", "inbound"], default="auto")

    webhook_server = subcommands.add_parser("brevo-webhook-server", help="Run local Brevo webhook receiver")
    webhook_server.add_argument("--host", default=None)
    webhook_server.add_argument("--port", type=int, default=None)

    send_followups = subcommands.add_parser("send-followups", help="Queue due follow-ups and send queued email")
    send_followups.add_argument("--dry-run", action="store_true")
    send_followups.add_argument("--no-delay", action="store_true")

    email_pipeline = subcommands.add_parser("email-pipeline", help="Find leads, queue cold email, and send within limits")
    email_pipeline.add_argument("--dry-run", action="store_true")
    email_pipeline.add_argument("--no-delay", action="store_true")
    email_pipeline.add_argument("--queue-only", action="store_true")

    subcommands.add_parser("send-summary", help="Send the 8PM daily summary email")
    cloud_scheduler = subcommands.add_parser("cloud-scheduler", help="Run the always-on cloud scheduler loop")
    cloud_scheduler.add_argument("--poll-seconds", type=int, default=60)
    subcommands.add_parser("render-service", help="Run the Render web service plus background scheduler")

    subcommands.add_parser("daily", help="Draft due follow-ups and write daily metrics report")
    subcommands.add_parser("list-leads", help="Print all leads as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = RevenueOpsConfig.from_env(args.data_dir)
    agent = RevenueAgent(config)
    email_campaign = EmailCampaign(config, agent.store)
    lead_finder = LeadFinder(config, agent.store)

    if args.command == "init":
        print(json.dumps({"ok": True, "data_dir": str(Path(config.data_dir).resolve())}, indent=2))
        return 0

    if args.command == "add-lead":
        lead = Lead(
            name=args.name,
            company=args.company,
            email=args.email,
            profile_url=args.profile_url,
            niche=args.niche,
            country=args.country,
            review_count=args.review_count,
            source=args.source,
            need=args.need,
            budget=args.budget,
            notes=args.notes,
            score=args.score,
        )
        print(json.dumps(agent.add_lead(lead).to_dict(), indent=2))
        return 0

    if args.command == "draft-outreach":
        print(json.dumps(agent.draft_outreach(args.lead_id).to_dict(), indent=2))
        return 0

    if args.command == "record-contact":
        print(json.dumps(agent.record_manual_contact(args.lead_id, args.message_id).to_dict(), indent=2))
        return 0

    if args.command == "record-event":
        print(json.dumps(agent.record_event(args.lead_id, args.kind, args.detail).to_dict(), indent=2))
        return 0

    if args.command == "record-feedback":
        print(json.dumps(agent.record_feedback(
            args.lead_id,
            args.message_id,
            args.rating,
            args.notes,
            args.sounded_like_you,
            args.make_better,
            args.would_pay_9,
        ).to_dict(), indent=2))
        return 0

    if args.command == "import-csv":
        print(json.dumps(agent.import_csv(args.path), indent=2))
        return 0

    if args.command == "dashboard":
        from .dashboard.server import run_server

        run_server(args.host, args.port)
        return 0

    if args.command == "find-leads":
        print(json.dumps(lead_finder.run_all(), indent=2))
        return 0

    if args.command == "queue-emails":
        print(json.dumps(email_campaign.queue_new_outreach(), indent=2))
        return 0

    if args.command == "send-emails":
        print(json.dumps(email_campaign.send_queued(max_to_send=args.max, dry_run=args.dry_run, no_delay=args.no_delay), indent=2))
        return 0

    if args.command == "check-replies":
        print(json.dumps(email_campaign.check_replies(), indent=2))
        return 0

    if args.command == "process-brevo-webhook":
        from .brevo_webhooks import BrevoWebhookProcessor

        print(json.dumps(BrevoWebhookProcessor(config, agent.store).process_file(args.path, args.kind), indent=2))
        return 0

    if args.command == "brevo-webhook-server":
        from .brevo_webhook_server import run_server

        if args.host:
            config.webhook_host = args.host
        if args.port:
            config.webhook_port = args.port
        run_server(config)
        return 0

    if args.command == "send-followups":
        queued = email_campaign.queue_followups()
        sent = email_campaign.send_queued(dry_run=args.dry_run, no_delay=args.no_delay)
        print(json.dumps({"queued": queued, "sent": sent}, indent=2))
        return 0

    if args.command == "email-pipeline":
        found = lead_finder.run_all()
        run = email_campaign.run_pipeline(send=not args.queue_only, dry_run=args.dry_run, no_delay=args.no_delay)
        print(json.dumps({"found": found, **run}, indent=2))
        return 0

    if args.command == "send-summary":
        print(json.dumps(email_campaign.send_summary_email(), indent=2))
        return 0

    if args.command == "cloud-scheduler":
        from .cloud_scheduler import CloudScheduler

        CloudScheduler(config).run_forever(poll_seconds=args.poll_seconds)
        return 0

    if args.command == "render-service":
        from .render_service import run_render_service

        run_render_service()
        return 0

    if args.command == "daily":
        print(json.dumps(agent.run_daily(), indent=2))
        return 0

    if args.command == "list-leads":
        print(json.dumps([lead.to_dict() for lead in agent.store.leads.all()], indent=2))
        return 0

    parser.print_help()
    return 0
