"""Apex Predator deployment package.

Contains VPS install scripts, systemd units, cron templates, and the
background-task runner. Not part of the importable runtime; lives here
so ``python -m deploy.scripts.run_task`` works from the repo root.
"""
