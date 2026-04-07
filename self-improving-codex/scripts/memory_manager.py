#!/usr/bin/env python3
"""
Manage self-improving Codex memory, summaries, snapshots, and rollback.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SKILL_NAME = "self-improving-codex"
DEFAULT_KEEP_DAYS = 180
SNAPSHOT_INTERVAL = timedelta(hours=2)
MARKER_FILE = ".self-improving-codex-root"


def default_memory_root() -> Path:
    return Path.home() / ".codex" / "memories" / SKILL_NAME


def parse_now(raw: str | None) -> datetime:
    if raw:
        value = raw.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError("--now must include timezone information")
        return parsed
    return datetime.now().astimezone()


def isoformat_seconds(when: datetime) -> str:
    return when.isoformat(timespec="seconds")


def snapshot_id_from_dt(when: datetime) -> str:
    offset = when.strftime("%z")
    if offset:
        offset = f"{offset[:3]}-{offset[3:]}"
    else:
        offset = "+00-00"
    return f"{when.strftime('%Y-%m-%dT%H-%M-%S')}{offset}"


def normalize_key(text: str) -> str:
    chars = []
    for char in text.lower().strip():
        chars.append(char if char.isalnum() else "-")
    normalized = "".join(chars)
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized.strip("-") or "untitled"


class MemoryManager:
    def __init__(self, root: Path):
        self.root = self.validate_root(root)
        self.marker_path = self.root / MARKER_FILE
        self.catalog_dir = self.root / "catalog"
        self.journal_dir = self.root / "journal"
        self.summaries_dir = self.root / "summaries"
        self.snapshots_dir = self.root / "snapshots"
        self.state_path = self.root / "state.json"
        self.observations_path = self.catalog_dir / "observations.jsonl"
        self.learnings_path = self.catalog_dir / "learnings.json"
        self.errors_path = self.catalog_dir / "errors.json"
        self.feature_requests_path = self.catalog_dir / "feature_requests.json"

    def validate_root(self, root: Path) -> Path:
        resolved = root.expanduser().resolve()
        codex_home = (Path.home() / ".codex").resolve()
        allowed_roots = [
            (codex_home / "memories").resolve(),
            (codex_home / ".tmp").resolve(),
        ]
        for allowed_root in allowed_roots:
            if resolved == allowed_root or allowed_root in resolved.parents:
                return resolved
        raise ValueError(
            "memory_root must live under ~/.codex/memories or ~/.codex/.tmp to keep rollback bounded"
        )

    def initialize(self, now: datetime) -> dict[str, Any]:
        created: list[str] = []
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in [
            self.catalog_dir,
            self.journal_dir,
            self.summaries_dir,
            self.snapshots_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            self.write_state(
                {
                    "schema_version": 1,
                    "timezone": now.strftime("%z") or "+0000",
                    "last_snapshot_at": None,
                    "last_summary_date": None,
                    "last_preflight_at": None,
                    "last_record_at": None,
                    "last_restored_at": None,
                    "last_restored_from": None,
                }
            )
            created.append(str(self.state_path))
        if not self.marker_path.exists():
            self.marker_path.write_text(
                "Managed by self-improving-codex. Destructive operations must stay inside this root.\n",
                encoding="utf-8",
            )
            created.append(str(self.marker_path))
        for path in [self.learnings_path, self.errors_path, self.feature_requests_path]:
            if not path.exists():
                self.write_json(path, {"entries": []})
                created.append(str(path))
        if not self.observations_path.exists():
            self.observations_path.write_text("", encoding="utf-8")
            created.append(str(self.observations_path))
        profile_path = self.root / "PROFILE.md"
        if not profile_path.exists():
            profile_path.write_text(self.render_profile(now), encoding="utf-8")
            created.append(str(profile_path))
        self.render_managed_markdown(now)
        return {"created": created, "memory_root": str(self.root)}

    def require_managed_root(self, allow_unsafe_root: bool = False) -> None:
        if not self.root.exists() or not self.marker_path.exists():
            raise RuntimeError(
                f"Managed memory root marker missing at {self.marker_path}. "
                "Run init first or use the intended self-improving-codex memory root."
            )
        canonical = default_memory_root().resolve()
        actual = self.root.resolve()
        if actual != canonical and not allow_unsafe_root:
            raise RuntimeError(
                f"Refusing destructive operation outside canonical memory root {canonical}. "
                "Re-run with --allow-unsafe-root only for isolated test roots."
            )

    def read_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    def state(self) -> dict[str, Any]:
        return self.read_json(self.state_path, {})

    def write_state(self, state: dict[str, Any]) -> None:
        self.write_json(self.state_path, state)

    def load_entries(self, path: Path) -> list[dict[str, Any]]:
        return self.read_json(path, {"entries": []}).get("entries", [])

    def save_entries(self, path: Path, entries: list[dict[str, Any]]) -> None:
        self.write_json(path, {"entries": entries})

    def load_observations(self) -> list[dict[str, Any]]:
        observations: list[dict[str, Any]] = []
        if not self.observations_path.exists():
            return observations
        for raw_line in self.observations_path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if raw_line:
                observations.append(json.loads(raw_line))
        return observations

    def append_observation(self, payload: dict[str, Any]) -> None:
        with self.observations_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def render_profile(self, now: datetime) -> str:
        return (
            "# Profile\n\n"
            "Use this file for durable collaboration preferences and user-specific facts that should remain stable over time.\n\n"
            f"- Initialized: {isoformat_seconds(now)}\n"
            "- Prefer ACTIVE.md for current reminders and priorities.\n"
            "- Use the manager script instead of hand-editing generated files when possible.\n"
        )

    def render_managed_markdown(self, now: datetime) -> None:
        learnings = self.load_entries(self.learnings_path)
        errors = self.load_entries(self.errors_path)
        features = self.load_entries(self.feature_requests_path)
        state = self.state()
        (self.root / "LEARNINGS.md").write_text(
            self.render_promoted_file("Learnings", "Positive patterns that proved reusable.", learnings),
            encoding="utf-8",
        )
        (self.root / "ERRORS.md").write_text(
            self.render_promoted_file("Errors", "Failure modes and preventive guardrails.", errors),
            encoding="utf-8",
        )
        (self.root / "FEATURE_REQUESTS.md").write_text(
            self.render_feature_requests(features),
            encoding="utf-8",
        )
        (self.root / "ACTIVE.md").write_text(
            self.render_active(now, learnings, errors, features, state),
            encoding="utf-8",
        )

    def render_promoted_file(
        self, title: str, subtitle: str, entries: list[dict[str, Any]]
    ) -> str:
        lines = [f"# {title}", "", subtitle, ""]
        if not entries:
            lines.append("No promoted entries yet.")
            lines.append("")
            return "\n".join(lines)
        sorted_entries = sorted(
            entries,
            key=lambda item: (item.get("confidence", 0), item.get("applications", 0), item.get("last_validated", "")),
            reverse=True,
        )
        for entry in sorted_entries:
            lines.append(f"## {entry['title']}")
            lines.append("")
            lines.append(f"- Summary: {entry['summary']}")
            if entry.get("details"):
                lines.append(f"- Details: {entry['details']}")
            if entry.get("impact"):
                lines.append(f"- Impact: {entry['impact']}")
            lines.append(f"- Confidence: {entry.get('confidence', 0):.2f}")
            lines.append(f"- Source dates: {', '.join(entry.get('source_dates', []))}")
            lines.append(f"- Applications: {entry.get('applications', 0)}")
            lines.append(f"- Last validated: {entry.get('last_validated', 'n/a')}")
            lines.append(f"- Evolution note: {entry.get('evolution_note', 'n/a')}")
            if entry.get("tags"):
                lines.append(f"- Tags: {', '.join(entry['tags'])}")
            lines.append("")
        return "\n".join(lines)

    def render_feature_requests(self, entries: list[dict[str, Any]]) -> str:
        lines = ["# Feature Requests", "", "Persistent follow-ups and ideas worth revisiting.", ""]
        if not entries:
            lines.append("No open feature requests.")
            lines.append("")
            return "\n".join(lines)
        sorted_entries = sorted(
            entries,
            key=lambda item: (item.get("status") != "open", item.get("last_requested", "")),
        )
        for entry in sorted_entries:
            lines.append(f"## {entry['title']}")
            lines.append("")
            lines.append(f"- Summary: {entry['summary']}")
            if entry.get("details"):
                lines.append(f"- Details: {entry['details']}")
            lines.append(f"- Status: {entry.get('status', 'open')}")
            lines.append(f"- Requests: {entry.get('occurrences', 0)}")
            lines.append(f"- Source dates: {', '.join(entry.get('source_dates', []))}")
            lines.append(f"- Last requested: {entry.get('last_requested', 'n/a')}")
            if entry.get("tags"):
                lines.append(f"- Tags: {', '.join(entry['tags'])}")
            lines.append("")
        return "\n".join(lines)

    def render_active(
        self,
        now: datetime,
        learnings: list[dict[str, Any]],
        errors: list[dict[str, Any]],
        features: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> str:
        lines = ["# Active Memory", ""]
        lines.append(f"- Updated: {isoformat_seconds(now)}")
        lines.append(f"- Last snapshot: {state.get('last_snapshot_at') or 'never'}")
        lines.append(f"- Last summary date: {state.get('last_summary_date') or 'never'}")
        lines.append("")
        lines.append("## Operating Loop")
        lines.append("")
        lines.append("- Run `preflight` before substantive work.")
        lines.append("- Record only repeatable patterns, likely recurring errors, or explicitly accepted feature requests.")
        lines.append("- Prefer journals for raw observations and promoted files for repeatable rules.")
        lines.append("")
        lines.append("## Guardrails")
        lines.append("")
        top_errors = sorted(
            errors,
            key=lambda item: (item.get("confidence", 0), item.get("applications", 0)),
            reverse=True,
        )[:5]
        if top_errors:
            for entry in top_errors:
                lines.append(f"- {entry['title']}: {entry['summary']}")
        else:
            lines.append("- No promoted error guardrails yet.")
        lines.append("")
        lines.append("## Proven Patterns")
        lines.append("")
        top_learnings = sorted(
            learnings,
            key=lambda item: (item.get("confidence", 0), item.get("applications", 0)),
            reverse=True,
        )[:5]
        if top_learnings:
            for entry in top_learnings:
                lines.append(f"- {entry['title']}: {entry['summary']}")
        else:
            lines.append("- No promoted learnings yet.")
        lines.append("")
        lines.append("## Open Requests")
        lines.append("")
        open_requests = [entry for entry in features if entry.get("status", "open") == "open"][:5]
        if open_requests:
            for entry in open_requests:
                lines.append(f"- {entry['title']}: {entry['summary']}")
        else:
            lines.append("- No open feature requests.")
        lines.append("")
        return "\n".join(lines)

    def record(self, args: argparse.Namespace, now: datetime) -> dict[str, Any]:
        self.initialize(now)
        state = self.state()
        event_date = now.date().isoformat()
        if args.promote and args.kind not in {"learning", "error"}:
            raise ValueError("--promote is only supported for learning or error records")
        if args.promote and (not args.promotion_reason or args.confidence < 0.75):
            raise ValueError("--promote requires --promotion-reason and --confidence >= 0.75")
        event = {
            "id": snapshot_id_from_dt(now),
            "created_at": isoformat_seconds(now),
            "date": event_date,
            "kind": args.kind,
            "title": args.title.strip(),
            "summary": args.summary.strip(),
            "details": (args.details or "").strip(),
            "impact": (args.impact or "").strip(),
            "context": (args.context or "").strip(),
            "tags": args.tag or [],
            "confidence": args.confidence,
            "status": args.status,
            "promotion_reason": (args.promotion_reason or "").strip(),
            "key": normalize_key(f"{args.kind}-{args.title}"),
        }
        snapshot_result = self.snapshot(now, reason="pre-record-interval") if self.snapshot_due(now) else None
        self.append_observation(event)
        self.append_journal_entry(event, now)
        promoted = None
        if args.kind in {"learning", "error"}:
            promoted = self.maybe_promote(
                event,
                force=args.promote,
                promotion_reason=event["promotion_reason"],
            )
        elif args.kind == "feature-request":
            promoted = self.maybe_accept_feature_request(
                event,
                accept=args.accept_feature_request,
            )
        state["last_record_at"] = isoformat_seconds(now)
        self.write_state(state)
        self.render_managed_markdown(now)
        return {
            "recorded": event,
            "promoted": promoted,
            "snapshot": snapshot_result,
        }

    def append_journal_entry(self, event: dict[str, Any], now: datetime) -> None:
        journal_path = self.journal_dir / f"{event['date']}.md"
        if not journal_path.exists():
            journal_path.write_text(
                f"# Journal {event['date']}\n\nGenerated by {SKILL_NAME}.\n\n",
                encoding="utf-8",
            )
        lines = [
            f"## {now.strftime('%H:%M:%S')} {event['kind']}",
            "",
            f"- Title: {event['title']}",
            f"- Summary: {event['summary']}",
            f"- Confidence: {event['confidence']:.2f}",
        ]
        if event.get("details"):
            lines.append(f"- Details: {event['details']}")
        if event.get("impact"):
            lines.append(f"- Impact: {event['impact']}")
        if event.get("context"):
            lines.append(f"- Context: {event['context']}")
        if event.get("status") and event["kind"] == "feature-request":
            lines.append(f"- Status: {event['status']}")
        if event.get("tags"):
            lines.append(f"- Tags: {', '.join(event['tags'])}")
        lines.append("")
        with journal_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))

    def maybe_promote(
        self,
        event: dict[str, Any],
        force: bool,
        promotion_reason: str,
    ) -> dict[str, Any] | None:
        observations = [
            item
            for item in self.load_observations()
            if item["kind"] == event["kind"] and item["key"] == event["key"]
        ]
        distinct_dates = sorted({item["date"] for item in observations})
        best_confidence = max(float(item.get("confidence", 0.0)) for item in observations)
        should_promote = force or (len(distinct_dates) >= 2 and best_confidence >= 0.6)
        if not should_promote:
            return None
        target_path = self.learnings_path if event["kind"] == "learning" else self.errors_path
        entries = self.load_entries(target_path)
        existing = next((entry for entry in entries if entry["key"] == event["key"]), None)
        applications = len(observations)
        confidence = min(0.95, round(best_confidence + max(0, len(distinct_dates) - 2) * 0.1, 2))
        if force:
            evolution_note = (
                f"Promoted by explicit override for reason: {promotion_reason}. "
                f"Last updated on {event['date']}."
            )
        else:
            evolution_note = (
                f"Promoted from repeated observations across {len(distinct_dates)} distinct day(s); "
                f"last updated on {event['date']}."
            )
        payload = {
            "key": event["key"],
            "title": event["title"],
            "summary": existing["summary"] if existing and not force else event["summary"],
            "details": existing.get("details", "") if existing and not force else event["details"],
            "impact": existing.get("impact", "") if existing and not force else event["impact"],
            "tags": sorted({tag for item in observations for tag in item.get("tags", [])}),
            "confidence": confidence,
            "source_dates": distinct_dates,
            "applications": applications,
            "last_validated": event["date"],
            "evolution_note": evolution_note,
            "created_at": existing.get("created_at", event["created_at"]) if existing else event["created_at"],
            "updated_at": event["created_at"],
        }
        if existing:
            existing.update(payload)
        else:
            entries.append(payload)
        self.save_entries(target_path, entries)
        return payload

    def maybe_accept_feature_request(
        self,
        event: dict[str, Any],
        accept: bool,
    ) -> dict[str, Any] | None:
        observations = [
            item
            for item in self.load_observations()
            if item["kind"] == "feature-request" and item["key"] == event["key"]
        ]
        distinct_dates = sorted({item["date"] for item in observations})
        existing_entries = self.load_entries(self.feature_requests_path)
        existing = next((entry for entry in existing_entries if entry["key"] == event["key"]), None)
        should_accept = accept or existing is not None or len(distinct_dates) >= 2
        if not should_accept:
            return None
        return self.upsert_feature_request(event, existing_entries, existing)

    def upsert_feature_request(
        self,
        event: dict[str, Any],
        entries: list[dict[str, Any]] | None = None,
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entries = entries if entries is not None else self.load_entries(self.feature_requests_path)
        existing = existing or next((entry for entry in entries if entry["key"] == event["key"]), None)
        if existing:
            source_dates = sorted(set(existing.get("source_dates", []) + [event["date"]]))
            tags = sorted(set(existing.get("tags", []) + event.get("tags", [])))
            existing.update(
                {
                    "summary": event["summary"],
                    "details": event["details"] or existing.get("details", ""),
                    "status": event["status"],
                    "source_dates": source_dates,
                    "last_requested": event["date"],
                    "occurrences": int(existing.get("occurrences", 0)) + 1,
                    "tags": tags,
                    "updated_at": event["created_at"],
                }
            )
            payload = existing
        else:
            payload = {
                "key": event["key"],
                "title": event["title"],
                "summary": event["summary"],
                "details": event["details"],
                "status": event["status"],
                "source_dates": [event["date"]],
                "last_requested": event["date"],
                "occurrences": 1,
                "tags": event.get("tags", []),
                "created_at": event["created_at"],
                "updated_at": event["created_at"],
            }
            entries.append(payload)
        self.save_entries(self.feature_requests_path, entries)
        return payload

    def preflight(self, now: datetime) -> dict[str, Any]:
        self.initialize(now)
        state = self.state()
        summaries = self.backfill_summaries(now)
        snapshot_result = None
        if self.snapshot_due(now):
            snapshot_result = self.snapshot(now, reason="interval")
        state = self.state()
        state["last_preflight_at"] = isoformat_seconds(now)
        self.write_state(state)
        self.render_managed_markdown(now)
        return {
            "summaries": summaries,
            "snapshot": snapshot_result,
            "state": self.state(),
        }

    def backfill_summaries(self, now: datetime) -> list[dict[str, Any]]:
        observations = self.load_observations()
        if not observations:
            return []
        state = self.state()
        last_summary_date = state.get("last_summary_date")
        last_summary = datetime.fromisoformat(f"{last_summary_date}T00:00:00") if last_summary_date else None
        yesterday = now.date() - timedelta(days=1)
        candidate_dates = sorted(
            {
                datetime.fromisoformat(item["date"]).date()
                for item in observations
                if datetime.fromisoformat(item["date"]).date() <= yesterday
            }
        )
        if last_summary is not None:
            candidate_dates = [day for day in candidate_dates if day > last_summary.date()]
        generated = []
        for day in candidate_dates:
            summary_path = self.summaries_dir / f"{day.isoformat()}.md"
            if not summary_path.exists():
                summary_payload = self.generate_summary(day.isoformat(), now)
                summary_path.write_text(summary_payload["markdown"], encoding="utf-8")
                generated.append(summary_payload)
            state["last_summary_date"] = day.isoformat()
        if candidate_dates:
            self.write_state(state)
        return generated

    def generate_summary(self, day: str, now: datetime) -> dict[str, Any]:
        observations = [item for item in self.load_observations() if item["date"] == day]
        learnings = [item for item in observations if item["kind"] == "learning"]
        errors = [item for item in observations if item["kind"] == "error"]
        features = [item for item in observations if item["kind"] == "feature-request"]
        promoted_learnings = {
            entry["key"]: entry
            for entry in self.load_entries(self.learnings_path)
            if day in entry.get("source_dates", [])
        }
        promoted_errors = {
            entry["key"]: entry
            for entry in self.load_entries(self.errors_path)
            if day in entry.get("source_dates", [])
        }
        lines = [f"# Daily Summary {day}", ""]
        lines.append(f"- Generated at: {isoformat_seconds(now)}")
        lines.append(f"- Total events: {len(observations)}")
        lines.append(f"- Learnings: {len(learnings)}")
        lines.append(f"- Errors: {len(errors)}")
        lines.append(f"- Feature requests: {len(features)}")
        lines.append("")
        lines.append("## Highlights")
        lines.append("")
        for event in (learnings + errors + features)[:8]:
            lines.append(f"- {event['kind']}: {event['title']} - {event['summary']}")
        if len(observations) == 0:
            lines.append("- No recorded events.")
        lines.append("")
        lines.append("## Promotions")
        lines.append("")
        promotions = list(promoted_learnings.values()) + list(promoted_errors.values())
        if promotions:
            for entry in promotions:
                lines.append(f"- {entry['title']}: confidence {entry['confidence']:.2f}")
        else:
            lines.append("- No new stable promotions from this day yet.")
        lines.append("")
        return {
            "date": day,
            "markdown": "\n".join(lines),
        }

    def snapshot_due(self, now: datetime) -> bool:
        state = self.state()
        last_snapshot_raw = state.get("last_snapshot_at")
        if not last_snapshot_raw:
            return True
        last_snapshot = datetime.fromisoformat(last_snapshot_raw)
        return now - last_snapshot >= SNAPSHOT_INTERVAL

    def snapshot(self, now: datetime, reason: str = "manual") -> dict[str, Any]:
        self.initialize(now)
        self.render_managed_markdown(now)
        state = self.state()
        snapshot_id = snapshot_id_from_dt(now)
        manifest_path = self.snapshots_dir / f"{snapshot_id}.json"
        archive_path = self.snapshots_dir / f"{snapshot_id}.zip"
        suffix = 1
        while manifest_path.exists() or archive_path.exists():
            snapshot_id = f"{snapshot_id_from_dt(now)}-{suffix}"
            manifest_path = self.snapshots_dir / f"{snapshot_id}.json"
            archive_path = self.snapshots_dir / f"{snapshot_id}.zip"
            suffix += 1
        temp_archive_path = archive_path.with_suffix(".zip.tmp")
        temp_manifest_path = manifest_path.with_suffix(".json.tmp")
        with zipfile.ZipFile(temp_archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.root.rglob("*")):
                if self.snapshots_dir in path.parents or path == self.snapshots_dir:
                    continue
                if path.is_file():
                    archive.write(path, path.relative_to(self.root).as_posix())
        manifest = {
            "id": snapshot_id,
            "created_at": isoformat_seconds(now),
            "reason": reason,
            "archive": archive_path.name,
            "schema_version": state.get("schema_version", 1),
        }
        self.write_json(temp_manifest_path, manifest)
        temp_archive_path.replace(archive_path)
        temp_manifest_path.replace(manifest_path)
        state["last_snapshot_at"] = isoformat_seconds(now)
        self.write_state(state)
        return manifest

    def list_snapshots(self) -> list[dict[str, Any]]:
        manifests = []
        for path in sorted(self.snapshots_dir.glob("*.json"), reverse=True):
            manifests.append(self.read_json(path, {}))
        return manifests

    def rollback(self, snapshot_id: str, now: datetime, allow_unsafe_root: bool = False) -> dict[str, Any]:
        self.require_managed_root(allow_unsafe_root=allow_unsafe_root)
        target_manifest_path = self.snapshots_dir / f"{snapshot_id}.json"
        target_archive_path = self.snapshots_dir / f"{snapshot_id}.zip"
        if not target_manifest_path.exists() or not target_archive_path.exists():
            raise FileNotFoundError(f"Snapshot '{snapshot_id}' not found")
        rescue = self.snapshot(now, reason=f"pre-rollback:{snapshot_id}")
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            with zipfile.ZipFile(target_archive_path, "r") as archive:
                for member in archive.namelist():
                    target = tmp_root / member
                    resolved = target.resolve()
                    if tmp_root.resolve() not in resolved.parents and resolved != tmp_root.resolve():
                        raise RuntimeError("Unsafe snapshot entry detected")
                archive.extractall(tmp_root)
            for path in list(self.root.iterdir()):
                if path.name == "snapshots":
                    continue
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            for path in tmp_root.rglob("*"):
                relative = path.relative_to(tmp_root)
                destination = self.root / relative
                if path.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, destination)
        state = self.state()
        state["last_restored_at"] = isoformat_seconds(now)
        state["last_restored_from"] = snapshot_id
        self.write_state(state)
        self.render_managed_markdown(now)
        return {"restored_from": snapshot_id, "rescue_snapshot": rescue}

    def prune(self, keep_days: int, now: datetime, allow_unsafe_root: bool = False) -> dict[str, Any]:
        self.require_managed_root(allow_unsafe_root=allow_unsafe_root)
        cutoff = now - timedelta(days=keep_days)
        removed = []
        for manifest in self.list_snapshots():
            created_at = datetime.fromisoformat(manifest["created_at"])
            if created_at < cutoff:
                manifest_path = self.snapshots_dir / f"{manifest['id']}.json"
                archive_path = self.snapshots_dir / f"{manifest['id']}.zip"
                if manifest_path.exists():
                    manifest_path.unlink()
                if archive_path.exists():
                    archive_path.unlink()
                removed.append(manifest["id"])
        return {"removed": removed, "keep_days": keep_days}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage self-improving Codex memory")
    parser.add_argument("--memory-root", type=Path, default=default_memory_root())
    parser.add_argument("--now")
    parser.add_argument("--allow-unsafe-root", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init")
    subparsers.add_parser("preflight")

    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--kind", choices=["learning", "error", "feature-request", "note"], required=True)
    record_parser.add_argument("--title", required=True)
    record_parser.add_argument("--summary", required=True)
    record_parser.add_argument("--details")
    record_parser.add_argument("--impact")
    record_parser.add_argument("--context")
    record_parser.add_argument("--tag", action="append")
    record_parser.add_argument("--confidence", type=float, default=0.6)
    record_parser.add_argument("--promote", action="store_true")
    record_parser.add_argument("--promotion-reason")
    record_parser.add_argument("--accept-feature-request", action="store_true")
    record_parser.add_argument("--status", default="open")

    snapshot_parser = subparsers.add_parser("snapshot")
    snapshot_parser.add_argument("--reason", default="manual")

    list_parser = subparsers.add_parser("list-snapshots")
    list_parser.add_argument("--json", action="store_true")

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--id", required=True)

    prune_parser = subparsers.add_parser("prune")
    prune_parser.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS)
    return parser


def emit(result: Any, as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
        return
    for entry in result:
        print(f"{entry['id']}  {entry['created_at']}  {entry['reason']}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        now = parse_now(args.now)
        manager = MemoryManager(args.memory_root)

        if args.command == "init":
            emit(manager.initialize(now))
            return 0
        if args.command == "preflight":
            emit(manager.preflight(now))
            return 0
        if args.command == "record":
            emit(manager.record(args, now))
            return 0
        if args.command == "snapshot":
            emit(manager.snapshot(now, reason=args.reason))
            return 0
        if args.command == "list-snapshots":
            result = manager.list_snapshots()
            emit(result, as_json=args.json)
            return 0
        if args.command == "rollback":
            emit(manager.rollback(args.id, now, allow_unsafe_root=args.allow_unsafe_root))
            return 0
        if args.command == "prune":
            emit(manager.prune(args.keep_days, now, allow_unsafe_root=args.allow_unsafe_root))
            return 0
        parser.error("Unknown command")
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
