import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <job>")
        print("  Jobs: slack-sync | weekly-notify | monthly-report")
        sys.exit(1)

    job = sys.argv[1]

    if job == "slack-sync":
        from jobs.slack_sync import run
    elif job == "weekly-notify":
        from jobs.weekly_notify import run
    elif job == "monthly-report":
        from jobs.monthly_report import run
    else:
        print(f"Unknown job: {job}")
        sys.exit(1)

    run()


if __name__ == "__main__":
    main()
