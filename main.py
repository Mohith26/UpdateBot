import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <job> [options]")
        print("  Jobs: slack-sync | weekly-notify | monthly-report")
        print("  Options:")
        print("    monthly-report --dry-run   Resolve and print placeholders without writing Slides or posting to Slack")
        sys.exit(1)

    job = sys.argv[1]
    args = sys.argv[2:]

    if job == "slack-sync":
        from jobs.slack_sync import run
        run()
    elif job == "weekly-notify":
        from jobs.weekly_notify import run
        run()
    elif job == "monthly-report":
        from jobs.monthly_report import run
        dry_run = "--dry-run" in args
        run(dry_run=dry_run)
    else:
        print(f"Unknown job: {job}")
        sys.exit(1)


if __name__ == "__main__":
    main()
