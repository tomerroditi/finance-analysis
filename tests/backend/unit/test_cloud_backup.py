"""Tests for cloud backup utility — retention policy and bundle creation."""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, call
import threading

from backend.config import AppConfig
from backend.utils.cloud_backup import compute_backups_to_prune, BackupScheduler


class TestTieredRetention:
    """Tests for the tiered retention pruning algorithm."""

    def test_keeps_5_most_recent(self):
        """Should never prune the 5 most recent backups."""
        now = datetime(2026, 4, 4, 12, 0, 0)
        backups = [
            {"id": f"b{i}", "name": (now - timedelta(hours=i)).strftime("%Y%m%d_%H%M%S")}
            for i in range(7)
        ]
        to_prune = compute_backups_to_prune(backups)
        pruned_ids = {b["id"] for b in to_prune}
        for i in range(5):
            assert f"b{i}" not in pruned_ids

    def test_keeps_one_per_week_for_older(self):
        """Should keep only the newest backup per ISO week for backups older than the 5th."""
        now = datetime(2026, 4, 4, 12, 0, 0)
        backups = []
        for i in range(5):
            backups.append({
                "id": f"recent-{i}",
                "name": (now - timedelta(hours=i)).strftime("%Y%m%d_%H%M%S"),
            })
        week_start = now - timedelta(weeks=2)
        for i in range(3):
            backups.append({
                "id": f"old-{i}",
                "name": (week_start + timedelta(hours=i)).strftime("%Y%m%d_%H%M%S"),
            })

        to_prune = compute_backups_to_prune(backups)
        pruned_ids = {b["id"] for b in to_prune}
        assert "old-2" not in pruned_ids
        assert "old-0" in pruned_ids
        assert "old-1" in pruned_ids

    def test_prunes_backups_older_than_12_weeks(self):
        """Should prune weekly backups older than 12 weeks."""
        now = datetime(2026, 4, 4, 12, 0, 0)
        backups = []
        for i in range(5):
            backups.append({
                "id": f"recent-{i}",
                "name": (now - timedelta(hours=i)).strftime("%Y%m%d_%H%M%S"),
            })
        old_date = now - timedelta(weeks=13)
        backups.append({
            "id": "very-old",
            "name": old_date.strftime("%Y%m%d_%H%M%S"),
        })

        to_prune = compute_backups_to_prune(backups)
        pruned_ids = {b["id"] for b in to_prune}
        assert "very-old" in pruned_ids

    def test_no_pruning_when_under_5(self):
        """Should not prune anything when there are 5 or fewer backups."""
        backups = [
            {"id": f"b{i}", "name": f"2026040{i}_120000"}
            for i in range(4)
        ]
        to_prune = compute_backups_to_prune(backups)
        assert len(to_prune) == 0

    def test_empty_list(self):
        """Should handle empty backup list."""
        assert compute_backups_to_prune([]) == []


class TestBackupScheduler:
    """Tests for the debounce-based backup scheduler."""

    def test_schedule_creates_timer(self):
        """Should create a timer when schedule is called."""
        mock_drive_service = MagicMock()
        scheduler = BackupScheduler(mock_drive_service)
        scheduler.schedule()
        assert scheduler._timer is not None
        assert scheduler._timer.is_alive()
        scheduler.cancel()

    def test_schedule_resets_timer_on_subsequent_calls(self):
        """Should cancel previous timer and create new one."""
        mock_drive_service = MagicMock()
        scheduler = BackupScheduler(mock_drive_service, debounce_seconds=300)
        scheduler.schedule()
        first_timer = scheduler._timer
        scheduler.schedule()
        second_timer = scheduler._timer
        assert first_timer is not second_timer
        assert first_timer.finished.is_set()
        assert second_timer.is_alive()
        scheduler.cancel()

    def test_cancel_stops_timer(self):
        """Should cancel the pending timer."""
        mock_drive_service = MagicMock()
        scheduler = BackupScheduler(mock_drive_service)
        scheduler.schedule()
        scheduler.cancel()
        assert scheduler._timer is None or not scheduler._timer.is_alive()

    def test_is_pending(self):
        """Should report whether a backup is pending."""
        mock_drive_service = MagicMock()
        scheduler = BackupScheduler(mock_drive_service)
        assert scheduler.is_pending is False
        scheduler.schedule()
        assert scheduler.is_pending is True
        scheduler.cancel()
        assert scheduler.is_pending is False

    def test_does_not_schedule_in_demo_mode(self):
        """Should not create a timer when in demo mode."""
        mock_drive_service = MagicMock()
        scheduler = BackupScheduler(mock_drive_service)
        config = AppConfig()
        config.set_demo_mode(True)
        try:
            scheduler.schedule()
            assert scheduler._timer is None
        finally:
            config.set_demo_mode(False)

    def test_does_not_schedule_when_not_connected(self):
        """Should not create a timer when Google is not connected."""
        mock_drive_service = MagicMock()
        mock_drive_service.is_connected.return_value = False
        scheduler = BackupScheduler(mock_drive_service)
        scheduler.schedule()
        assert scheduler._timer is None
