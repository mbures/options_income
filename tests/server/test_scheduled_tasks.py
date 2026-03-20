"""Tests for scheduled background tasks.

Tests task execution, market hours logic, and task registration.
"""

from datetime import datetime, time, timedelta
from unittest.mock import MagicMock, patch

import pytest
import pytz
from fastapi.testclient import TestClient

from src.server.database.models.snapshot import Snapshot
from src.server.database.models.trade import Trade
from src.server.tasks.market_hours import (
    get_next_market_close,
    get_next_market_open,
    is_market_open,
    should_run_task,
)
from src.server.tasks.scheduled_tasks import (
    auto_expire_trades_task,
    daily_snapshot_task,
    opportunity_scanning_task,
    price_refresh_task,
    risk_monitoring_task,
)
from src.server.tasks.task_loader import register_core_tasks, unregister_core_tasks

EASTERN = pytz.timezone("America/New_York")


class TestMarketHours:
    """Test cases for market hours utilities."""

    def test_market_open_during_trading_hours(self):
        """Test market is open during trading hours on weekday."""
        # Wednesday at 2:00 PM ET
        test_time = EASTERN.localize(datetime(2026, 2, 4, 14, 0))
        assert is_market_open(test_time) is True

    def test_market_closed_before_open(self):
        """Test market is closed before 9:30 AM ET."""
        # Wednesday at 9:00 AM ET (before market open)
        test_time = EASTERN.localize(datetime(2026, 2, 4, 9, 0))
        assert is_market_open(test_time) is False

    def test_market_closed_after_close(self):
        """Test market is closed after 4:00 PM ET."""
        # Wednesday at 5:00 PM ET (after market close)
        test_time = EASTERN.localize(datetime(2026, 2, 4, 17, 0))
        assert is_market_open(test_time) is False

    def test_market_closed_on_saturday(self):
        """Test market is closed on Saturday."""
        # Saturday at 2:00 PM ET
        test_time = EASTERN.localize(datetime(2026, 2, 7, 14, 0))
        assert is_market_open(test_time) is False

    def test_market_closed_on_sunday(self):
        """Test market is closed on Sunday."""
        # Sunday at 2:00 PM ET
        test_time = EASTERN.localize(datetime(2026, 2, 8, 14, 0))
        assert is_market_open(test_time) is False

    def test_market_open_at_exact_open_time(self):
        """Test market is open at exactly 9:30 AM ET."""
        # Wednesday at 9:30 AM ET
        test_time = EASTERN.localize(datetime(2026, 2, 4, 9, 30))
        assert is_market_open(test_time) is True

    def test_market_closed_at_exact_close_time(self):
        """Test market is closed at exactly 4:00 PM ET."""
        # Wednesday at 4:00 PM ET
        test_time = EASTERN.localize(datetime(2026, 2, 4, 16, 0))
        assert is_market_open(test_time) is False

    def test_should_run_price_refresh_during_hours(self):
        """Test price refresh task should run during market hours."""
        test_time = EASTERN.localize(datetime(2026, 2, 4, 14, 0))
        assert should_run_task("price_refresh", test_time) is True

    def test_should_not_run_price_refresh_after_hours(self):
        """Test price refresh task should not run after market close."""
        test_time = EASTERN.localize(datetime(2026, 2, 4, 17, 0))
        assert should_run_task("price_refresh", test_time) is False

    def test_should_run_daily_snapshot_after_close(self):
        """Test daily snapshot should run after market close."""
        test_time = EASTERN.localize(datetime(2026, 2, 4, 17, 0))
        assert should_run_task("daily_snapshot", test_time) is True

    def test_should_not_run_daily_snapshot_before_close(self):
        """Test daily snapshot should not run before market close."""
        test_time = EASTERN.localize(datetime(2026, 2, 4, 14, 0))
        assert should_run_task("daily_snapshot", test_time) is False

    def test_get_next_market_open_same_day(self):
        """Test next market open is today if before 9:30 AM."""
        # Wednesday at 8:00 AM ET
        test_time = EASTERN.localize(datetime(2026, 2, 4, 8, 0))
        next_open = get_next_market_open(test_time)

        assert next_open.day == 4
        assert next_open.hour == 9
        assert next_open.minute == 30

    def test_get_next_market_open_next_day(self):
        """Test next market open is tomorrow if after 9:30 AM."""
        # Wednesday at 3:00 PM ET
        test_time = EASTERN.localize(datetime(2026, 2, 4, 15, 0))
        next_open = get_next_market_open(test_time)

        assert next_open.day == 5  # Thursday
        assert next_open.hour == 9
        assert next_open.minute == 30

    def test_get_next_market_open_skip_weekend(self):
        """Test next market open skips weekend."""
        # Friday at 5:00 PM ET
        test_time = EASTERN.localize(datetime(2026, 2, 6, 17, 0))
        next_open = get_next_market_open(test_time)

        assert next_open.weekday() == 0  # Monday
        assert next_open.day == 9
        assert next_open.hour == 9
        assert next_open.minute == 30

    def test_get_next_market_close_same_day(self):
        """Test next market close is today if before 4:00 PM."""
        # Wednesday at 2:00 PM ET
        test_time = EASTERN.localize(datetime(2026, 2, 4, 14, 0))
        next_close = get_next_market_close(test_time)

        assert next_close.day == 4
        assert next_close.hour == 16
        assert next_close.minute == 0

    def test_get_next_market_close_next_day(self):
        """Test next market close is tomorrow if after 4:00 PM."""
        # Wednesday at 5:00 PM ET
        test_time = EASTERN.localize(datetime(2026, 2, 4, 17, 0))
        next_close = get_next_market_close(test_time)

        assert next_close.day == 5  # Thursday
        assert next_close.hour == 16
        assert next_close.minute == 0


class TestPriceRefreshTask:
    """Test cases for price refresh task."""

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    def test_price_refresh_skips_when_market_closed(
        self, mock_session_factory, mock_market_open
    ):
        """Test price refresh task skips when market is closed."""
        mock_market_open.return_value = False

        # Should not raise exception, just return early
        price_refresh_task()

        # Session factory should not be called
        mock_session_factory.assert_not_called()

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    def test_price_refresh_runs_when_market_open(
        self, mock_service_class, mock_session_factory, mock_market_open
    ):
        """Test price refresh task runs when market is open."""
        mock_market_open.return_value = True

        # Mock database session
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db

        # Mock position service
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.total_count = 5
        mock_result.high_risk_count = 1
        mock_service.get_all_open_positions.return_value = mock_result
        mock_service_class.return_value = mock_service

        # Run task
        price_refresh_task()

        # Verify service was called with force_refresh=True
        mock_service.get_all_open_positions.assert_called_once_with(
            force_refresh=True
        )
        mock_db.close.assert_called_once()


class TestDailySnapshotTask:
    """Test cases for daily snapshot task."""

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    def test_daily_snapshot_skips_when_market_closed(
        self, mock_session_factory, mock_market_open
    ):
        """Test daily snapshot skips when market is closed."""
        mock_market_open.return_value = False

        daily_snapshot_task()

        mock_session_factory.assert_not_called()

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    def test_daily_snapshot_creates_snapshots(
        self, mock_session_factory, mock_market_open, client, test_db
    ):
        """Test daily snapshot creates snapshot records."""
        mock_market_open.return_value = True
        mock_session_factory.return_value = lambda: test_db

        # Create portfolio, wheel, and open trade
        portfolio = client.post(
            "/api/v1/portfolios/", json={"name": "Test Portfolio"}
        ).json()

        wheel = client.post(
            f"/api/v1/portfolios/{portfolio['id']}/wheels",
            json={
                "symbol": "AAPL",
                "capital_allocated": 20000.0,  # Sufficient for put assignment
                "profile": "conservative",
            },
        ).json()

        from datetime import date, timedelta

        expiration = (date.today() + timedelta(days=14)).strftime("%Y-%m-%d")
        trade = client.post(
            f"/api/v1/wheels/{wheel['id']}/trades",
            json={
                "direction": "put",
                "strike": 150.0,
                "expiration_date": expiration,
                "premium_per_share": 2.50,
                "contracts": 1,
            },
        ).json()

        # Mock price fetcher
        with patch(
            "src.wheel.monitor.PositionMonitor._fetch_current_price"
        ) as mock_fetch:
            mock_fetch.return_value = 155.0

            # Run task
            daily_snapshot_task()

        # Verify snapshot was created
        snapshots = test_db.query(Snapshot).filter(Snapshot.trade_id == trade["id"]).all()
        assert len(snapshots) == 1

        snapshot = snapshots[0]
        assert snapshot.current_price == 155.0
        assert snapshot.dte_calendar == 14


class TestRiskMonitoringTask:
    """Test cases for risk monitoring task."""

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    def test_risk_monitoring_skips_when_market_closed(
        self, mock_session_factory, mock_market_open
    ):
        """Test risk monitoring skips when market is closed."""
        mock_market_open.return_value = False

        risk_monitoring_task()

        mock_session_factory.assert_not_called()

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    def test_risk_monitoring_logs_high_risk_positions(
        self, mock_service_class, mock_session_factory, mock_market_open
    ):
        """Test risk monitoring logs warnings for high risk positions."""
        mock_market_open.return_value = True

        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db

        # Mock high risk position
        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.direction = "put"
        mock_position.strike = 150.0
        mock_position.risk_level = "HIGH"
        mock_position.dte_calendar = 5
        mock_position.moneyness_pct = -2.5

        mock_result = MagicMock()
        mock_result.positions = [mock_position]

        mock_service = MagicMock()
        mock_service.get_all_open_positions.return_value = mock_result
        mock_service_class.return_value = mock_service

        # Run task
        risk_monitoring_task()

        # Verify service was called
        mock_service.get_all_open_positions.assert_called_once()
        mock_db.close.assert_called_once()


class TestOpportunityScanningTask:
    """Test cases for opportunity scanning task."""

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    def test_opportunity_scanning_skips_when_market_closed(
        self, mock_session_factory, mock_market_open
    ):
        """Test opportunity scanning skips when market is closed."""
        mock_market_open.return_value = False

        opportunity_scanning_task()

        mock_session_factory.assert_not_called()


class TestTaskRegistration:
    """Test cases for task registration."""

    def test_register_core_tasks(self):
        """Test core tasks are registered successfully."""
        from src.server.services.scheduler_service import SchedulerService

        scheduler = SchedulerService(db_url="sqlite:///:memory:")
        from apscheduler.executors.pool import ThreadPoolExecutor
        from apscheduler.jobstores.memory import MemoryJobStore
        from apscheduler.schedulers.background import BackgroundScheduler

        jobstores = {"default": MemoryJobStore()}
        executors = {"default": ThreadPoolExecutor(max_workers=5)}
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }

        scheduler.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="America/New_York",
        )

        scheduler.start()

        # Register tasks
        register_core_tasks(scheduler)

        # Verify all tasks are registered
        jobs = scheduler.get_jobs()
        job_ids = [j.id for j in jobs]

        assert "price_refresh" in job_ids
        assert "risk_monitoring" in job_ids
        assert "daily_snapshot" in job_ids
        assert "opportunity_scanning_1000" in job_ids
        assert "opportunity_scanning_1130" in job_ids
        assert "opportunity_scanning_1300" in job_ids
        assert "opportunity_scanning_1430" in job_ids

        # Cleanup
        scheduler.shutdown(wait=False)

    def test_unregister_core_tasks(self):
        """Test core tasks can be unregistered."""
        from src.server.services.scheduler_service import SchedulerService

        scheduler = SchedulerService(db_url="sqlite:///:memory:")
        from apscheduler.executors.pool import ThreadPoolExecutor
        from apscheduler.jobstores.memory import MemoryJobStore
        from apscheduler.schedulers.background import BackgroundScheduler

        jobstores = {"default": MemoryJobStore()}
        executors = {"default": ThreadPoolExecutor(max_workers=5)}
        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 60,
        }

        scheduler.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone="America/New_York",
        )

        scheduler.start()

        # Register and then unregister
        register_core_tasks(scheduler)
        assert len(scheduler.get_jobs()) == 8  # 4 core + 4 scanning jobs

        unregister_core_tasks(scheduler)
        assert len(scheduler.get_jobs()) == 0

        # Cleanup
        scheduler.shutdown(wait=False)


class TestAutoExpireTradesTask:
    """Test cases for auto-expiration of trades past their expiration date."""

    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    @patch("src.server.tasks.scheduled_tasks.TradeRepository")
    def test_no_expired_trades_is_noop(
        self, mock_trade_repo_cls, mock_wheel_svc_cls, mock_pos_svc_cls,
        mock_session_factory,
    ):
        """Test task does nothing when there are no expired trades."""
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db

        mock_trade_repo = MagicMock()
        mock_trade_repo.list_open_trades.return_value = []
        mock_trade_repo_cls.return_value = mock_trade_repo

        auto_expire_trades_task()

        mock_wheel_svc_cls.return_value.expire_trade.assert_not_called()
        mock_db.close.assert_called_once()

    @patch("src.server.tasks.scheduled_tasks.datetime")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    @patch("src.server.tasks.scheduled_tasks.TradeRepository")
    def test_skips_future_expiration_trades(
        self, mock_trade_repo_cls, mock_wheel_svc_cls, mock_pos_svc_cls,
        mock_session_factory, mock_datetime,
    ):
        """Test task only processes trades past expiration, not future ones."""
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db
        mock_datetime.utcnow.return_value = datetime(2026, 2, 21)

        # Trade expiring in the future
        future_trade = MagicMock()
        future_trade.expiration_date = "2026-03-15"
        future_trade.symbol = "AAPL"

        mock_trade_repo = MagicMock()
        mock_trade_repo.list_open_trades.return_value = [future_trade]
        mock_trade_repo_cls.return_value = mock_trade_repo

        auto_expire_trades_task()

        mock_wheel_svc_cls.return_value.expire_trade.assert_not_called()

    @patch("src.server.tasks.scheduled_tasks.datetime")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    @patch("src.server.tasks.scheduled_tasks.TradeRepository")
    def test_expired_put_otm_expires_worthless(
        self, mock_trade_repo_cls, mock_wheel_svc_cls, mock_pos_svc_cls,
        mock_session_factory, mock_datetime,
    ):
        """Test expired put OTM results in expired_worthless outcome."""
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db
        mock_datetime.utcnow.return_value = datetime(2026, 2, 21)

        # RKLB PUT $61, price $76.58 -> OTM, expired worthless
        trade = MagicMock()
        trade.id = 1
        trade.symbol = "RKLB"
        trade.direction = "put"
        trade.strike = 61.0
        trade.expiration_date = "2026-02-20"

        mock_trade_repo = MagicMock()
        mock_trade_repo.list_open_trades.return_value = [trade]
        mock_trade_repo_cls.return_value = mock_trade_repo

        # Mock price fetch
        mock_monitor = MagicMock()
        mock_monitor._fetch_quote_data.return_value = {"lastPrice": 76.58}
        mock_pos_svc = MagicMock()
        mock_pos_svc.monitor = mock_monitor
        mock_pos_svc_cls.return_value = mock_pos_svc

        # Mock expire result
        mock_result = MagicMock()
        mock_result.outcome = "expired_worthless"
        mock_wheel_svc = MagicMock()
        mock_wheel_svc.expire_trade.return_value = mock_result
        mock_wheel_svc_cls.return_value = mock_wheel_svc

        auto_expire_trades_task()

        from src.server.models.trade import TradeExpireRequest

        mock_wheel_svc.expire_trade.assert_called_once_with(
            1, TradeExpireRequest(price_at_expiry=76.58)
        )

    @patch("src.server.tasks.scheduled_tasks.datetime")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    @patch("src.server.tasks.scheduled_tasks.TradeRepository")
    def test_expired_call_itm_called_away(
        self, mock_trade_repo_cls, mock_wheel_svc_cls, mock_pos_svc_cls,
        mock_session_factory, mock_datetime,
    ):
        """Test expired call ITM results in called_away outcome."""
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db
        mock_datetime.utcnow.return_value = datetime(2026, 2, 21)

        # NVDA CALL $190, price $190.33 -> ITM, called away
        trade = MagicMock()
        trade.id = 2
        trade.symbol = "NVDA"
        trade.direction = "call"
        trade.strike = 190.0
        trade.expiration_date = "2026-02-20"

        mock_trade_repo = MagicMock()
        mock_trade_repo.list_open_trades.return_value = [trade]
        mock_trade_repo_cls.return_value = mock_trade_repo

        mock_monitor = MagicMock()
        mock_monitor._fetch_quote_data.return_value = {"lastPrice": 190.33}
        mock_pos_svc = MagicMock()
        mock_pos_svc.monitor = mock_monitor
        mock_pos_svc_cls.return_value = mock_pos_svc

        mock_result = MagicMock()
        mock_result.outcome = "called_away"
        mock_wheel_svc = MagicMock()
        mock_wheel_svc.expire_trade.return_value = mock_result
        mock_wheel_svc_cls.return_value = mock_wheel_svc

        auto_expire_trades_task()

        from src.server.models.trade import TradeExpireRequest

        mock_wheel_svc.expire_trade.assert_called_once_with(
            2, TradeExpireRequest(price_at_expiry=190.33)
        )

    @patch("src.server.tasks.scheduled_tasks.datetime")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    @patch("src.server.tasks.scheduled_tasks.TradeRepository")
    def test_expired_put_itm_assigned(
        self, mock_trade_repo_cls, mock_wheel_svc_cls, mock_pos_svc_cls,
        mock_session_factory, mock_datetime,
    ):
        """Test expired put ITM results in assigned outcome."""
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db
        mock_datetime.utcnow.return_value = datetime(2026, 2, 21)

        # PUT $150, price $145 -> ITM, assigned
        trade = MagicMock()
        trade.id = 3
        trade.symbol = "AAPL"
        trade.direction = "put"
        trade.strike = 150.0
        trade.expiration_date = "2026-02-20"

        mock_trade_repo = MagicMock()
        mock_trade_repo.list_open_trades.return_value = [trade]
        mock_trade_repo_cls.return_value = mock_trade_repo

        mock_monitor = MagicMock()
        mock_monitor._fetch_quote_data.return_value = {"lastPrice": 145.0}
        mock_pos_svc = MagicMock()
        mock_pos_svc.monitor = mock_monitor
        mock_pos_svc_cls.return_value = mock_pos_svc

        mock_result = MagicMock()
        mock_result.outcome = "assigned"
        mock_wheel_svc = MagicMock()
        mock_wheel_svc.expire_trade.return_value = mock_result
        mock_wheel_svc_cls.return_value = mock_wheel_svc

        auto_expire_trades_task()

        from src.server.models.trade import TradeExpireRequest

        mock_wheel_svc.expire_trade.assert_called_once_with(
            3, TradeExpireRequest(price_at_expiry=145.0)
        )

    @patch("src.server.tasks.scheduled_tasks.datetime")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    @patch("src.server.tasks.scheduled_tasks.TradeRepository")
    def test_price_fetch_failure_skips_trade(
        self, mock_trade_repo_cls, mock_wheel_svc_cls, mock_pos_svc_cls,
        mock_session_factory, mock_datetime,
    ):
        """Test that price fetch failure skips the trade without crashing."""
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db
        mock_datetime.utcnow.return_value = datetime(2026, 2, 21)

        # Two expired trades - first will fail price fetch, second should succeed
        trade1 = MagicMock()
        trade1.id = 1
        trade1.symbol = "BADTICKER"
        trade1.direction = "put"
        trade1.strike = 100.0
        trade1.expiration_date = "2026-02-20"

        trade2 = MagicMock()
        trade2.id = 2
        trade2.symbol = "AAPL"
        trade2.direction = "put"
        trade2.strike = 150.0
        trade2.expiration_date = "2026-02-20"

        mock_trade_repo = MagicMock()
        mock_trade_repo.list_open_trades.return_value = [trade1, trade2]
        mock_trade_repo_cls.return_value = mock_trade_repo

        # First call raises, second succeeds
        mock_monitor = MagicMock()
        mock_monitor._fetch_quote_data.side_effect = [
            ValueError("No price data available"),
            {"lastPrice": 145.0},
        ]
        mock_pos_svc = MagicMock()
        mock_pos_svc.monitor = mock_monitor
        mock_pos_svc_cls.return_value = mock_pos_svc

        mock_result = MagicMock()
        mock_result.outcome = "assigned"
        mock_wheel_svc = MagicMock()
        mock_wheel_svc.expire_trade.return_value = mock_result
        mock_wheel_svc_cls.return_value = mock_wheel_svc

        # Should not raise
        auto_expire_trades_task()

        # Only the second trade should have been expired
        mock_wheel_svc.expire_trade.assert_called_once()

    @patch("src.server.tasks.scheduled_tasks.datetime")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    @patch("src.server.tasks.scheduled_tasks.TradeRepository")
    def test_call_itm_intraday_high_triggers_exercise(
        self, mock_trade_repo_cls, mock_wheel_svc_cls, mock_pos_svc_cls,
        mock_session_factory, mock_datetime,
    ):
        """Test call ITM via highPrice (closed OTM) still gets called_away."""
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db
        mock_datetime.utcnow.return_value = datetime(2026, 2, 21)

        # NVDA CALL $190, lastPrice $188 (OTM), but highPrice $192 (was ITM)
        trade = MagicMock()
        trade.id = 1
        trade.symbol = "NVDA"
        trade.direction = "call"
        trade.strike = 190.0
        trade.expiration_date = "2026-02-20"

        mock_trade_repo = MagicMock()
        mock_trade_repo.list_open_trades.return_value = [trade]
        mock_trade_repo_cls.return_value = mock_trade_repo

        mock_monitor = MagicMock()
        mock_monitor._fetch_quote_data.return_value = {
            "lastPrice": 188.0,
            "highPrice": 192.0,
            "lowPrice": 185.0,
        }
        mock_pos_svc = MagicMock()
        mock_pos_svc.monitor = mock_monitor
        mock_pos_svc_cls.return_value = mock_pos_svc

        mock_result = MagicMock()
        mock_result.outcome = "called_away"
        mock_wheel_svc = MagicMock()
        mock_wheel_svc.expire_trade.return_value = mock_result
        mock_wheel_svc_cls.return_value = mock_wheel_svc

        auto_expire_trades_task()

        from src.server.models.trade import TradeExpireRequest

        mock_wheel_svc.expire_trade.assert_called_once_with(
            1, TradeExpireRequest(price_at_expiry=192.0)
        )

    @patch("src.server.tasks.scheduled_tasks.datetime")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    @patch("src.server.tasks.scheduled_tasks.TradeRepository")
    def test_put_itm_intraday_low_triggers_assignment(
        self, mock_trade_repo_cls, mock_wheel_svc_cls, mock_pos_svc_cls,
        mock_session_factory, mock_datetime,
    ):
        """Test put ITM via lowPrice (closed OTM) still gets assigned."""
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db
        mock_datetime.utcnow.return_value = datetime(2026, 2, 21)

        # AAPL PUT $150, lastPrice $152 (OTM), but lowPrice $148 (was ITM)
        trade = MagicMock()
        trade.id = 1
        trade.symbol = "AAPL"
        trade.direction = "put"
        trade.strike = 150.0
        trade.expiration_date = "2026-02-20"

        mock_trade_repo = MagicMock()
        mock_trade_repo.list_open_trades.return_value = [trade]
        mock_trade_repo_cls.return_value = mock_trade_repo

        mock_monitor = MagicMock()
        mock_monitor._fetch_quote_data.return_value = {
            "lastPrice": 152.0,
            "highPrice": 155.0,
            "lowPrice": 148.0,
        }
        mock_pos_svc = MagicMock()
        mock_pos_svc.monitor = mock_monitor
        mock_pos_svc_cls.return_value = mock_pos_svc

        mock_result = MagicMock()
        mock_result.outcome = "assigned"
        mock_wheel_svc = MagicMock()
        mock_wheel_svc.expire_trade.return_value = mock_result
        mock_wheel_svc_cls.return_value = mock_wheel_svc

        auto_expire_trades_task()

        from src.server.models.trade import TradeExpireRequest

        mock_wheel_svc.expire_trade.assert_called_once_with(
            1, TradeExpireRequest(price_at_expiry=148.0)
        )

    @patch("src.server.tasks.scheduled_tasks.datetime")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    @patch("src.server.tasks.scheduled_tasks.TradeRepository")
    def test_falls_back_to_last_price_when_high_low_unavailable(
        self, mock_trade_repo_cls, mock_wheel_svc_cls, mock_pos_svc_cls,
        mock_session_factory, mock_datetime,
    ):
        """Test falls back to lastPrice when highPrice/lowPrice are None."""
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db
        mock_datetime.utcnow.return_value = datetime(2026, 2, 21)

        trade = MagicMock()
        trade.id = 1
        trade.symbol = "AAPL"
        trade.direction = "call"
        trade.strike = 150.0
        trade.expiration_date = "2026-02-20"

        mock_trade_repo = MagicMock()
        mock_trade_repo.list_open_trades.return_value = [trade]
        mock_trade_repo_cls.return_value = mock_trade_repo

        mock_monitor = MagicMock()
        mock_monitor._fetch_quote_data.return_value = {
            "lastPrice": 155.0,
        }
        mock_pos_svc = MagicMock()
        mock_pos_svc.monitor = mock_monitor
        mock_pos_svc_cls.return_value = mock_pos_svc

        mock_result = MagicMock()
        mock_result.outcome = "called_away"
        mock_wheel_svc = MagicMock()
        mock_wheel_svc.expire_trade.return_value = mock_result
        mock_wheel_svc_cls.return_value = mock_wheel_svc

        auto_expire_trades_task()

        from src.server.models.trade import TradeExpireRequest

        mock_wheel_svc.expire_trade.assert_called_once_with(
            1, TradeExpireRequest(price_at_expiry=155.0)
        )


class TestPriceRefreshIntradayExercise:
    """Test cases for intraday ITM auto-exercise in price refresh task."""

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    def test_itm_put_triggers_auto_exercise(
        self, mock_wheel_svc_cls, mock_service_class, mock_session_factory,
        mock_market_open,
    ):
        """Test ITM put position triggers auto-exercise at current price."""
        mock_market_open.return_value = True
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db

        # ITM put: current_price ($145) <= strike ($150)
        mock_position = MagicMock()
        mock_position.trade_id = 1
        mock_position.symbol = "AAPL"
        mock_position.direction = "put"
        mock_position.strike = 150.0
        mock_position.current_price = 145.0

        mock_result = MagicMock()
        mock_result.total_count = 1
        mock_result.high_risk_count = 1
        mock_result.positions = [mock_position]

        mock_service = MagicMock()
        mock_service.get_all_open_positions.return_value = mock_result
        mock_service_class.return_value = mock_service

        mock_wheel_svc = MagicMock()
        mock_wheel_svc_cls.return_value = mock_wheel_svc

        price_refresh_task()

        from src.server.models.trade import TradeExpireRequest

        mock_wheel_svc.expire_trade.assert_called_once_with(
            1, TradeExpireRequest(price_at_expiry=145.0)
        )

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    def test_itm_call_triggers_auto_exercise(
        self, mock_wheel_svc_cls, mock_service_class, mock_session_factory,
        mock_market_open,
    ):
        """Test ITM call position triggers auto-exercise at current price."""
        mock_market_open.return_value = True
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db

        # ITM call: current_price ($195) >= strike ($190)
        mock_position = MagicMock()
        mock_position.trade_id = 2
        mock_position.symbol = "NVDA"
        mock_position.direction = "call"
        mock_position.strike = 190.0
        mock_position.current_price = 195.0

        mock_result = MagicMock()
        mock_result.total_count = 1
        mock_result.high_risk_count = 1
        mock_result.positions = [mock_position]

        mock_service = MagicMock()
        mock_service.get_all_open_positions.return_value = mock_result
        mock_service_class.return_value = mock_service

        mock_wheel_svc = MagicMock()
        mock_wheel_svc_cls.return_value = mock_wheel_svc

        price_refresh_task()

        from src.server.models.trade import TradeExpireRequest

        mock_wheel_svc.expire_trade.assert_called_once_with(
            2, TradeExpireRequest(price_at_expiry=195.0)
        )

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    def test_otm_position_not_exercised(
        self, mock_wheel_svc_cls, mock_service_class, mock_session_factory,
        mock_market_open,
    ):
        """Test OTM position is not auto-exercised."""
        mock_market_open.return_value = True
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db

        # OTM put: current_price ($155) > strike ($150)
        mock_position = MagicMock()
        mock_position.trade_id = 1
        mock_position.symbol = "AAPL"
        mock_position.direction = "put"
        mock_position.strike = 150.0
        mock_position.current_price = 155.0

        mock_result = MagicMock()
        mock_result.total_count = 1
        mock_result.high_risk_count = 0
        mock_result.positions = [mock_position]

        mock_service = MagicMock()
        mock_service.get_all_open_positions.return_value = mock_result
        mock_service_class.return_value = mock_service

        mock_wheel_svc = MagicMock()
        mock_wheel_svc_cls.return_value = mock_wheel_svc

        price_refresh_task()

        mock_wheel_svc.expire_trade.assert_not_called()

    @patch("src.server.tasks.scheduled_tasks.is_market_open")
    @patch("src.server.tasks.scheduled_tasks.get_session_factory")
    @patch("src.server.tasks.scheduled_tasks.PositionMonitorService")
    @patch("src.server.tasks.scheduled_tasks.WheelService")
    def test_exercise_failure_does_not_block_others(
        self, mock_wheel_svc_cls, mock_service_class, mock_session_factory,
        mock_market_open,
    ):
        """Test exercise failure on one position doesn't block others."""
        mock_market_open.return_value = True
        mock_db = MagicMock()
        mock_session_factory.return_value = lambda: mock_db

        # Two ITM puts
        position1 = MagicMock()
        position1.trade_id = 1
        position1.symbol = "AAPL"
        position1.direction = "put"
        position1.strike = 150.0
        position1.current_price = 145.0

        position2 = MagicMock()
        position2.trade_id = 2
        position2.symbol = "MSFT"
        position2.direction = "put"
        position2.strike = 400.0
        position2.current_price = 390.0

        mock_result = MagicMock()
        mock_result.total_count = 2
        mock_result.high_risk_count = 2
        mock_result.positions = [position1, position2]

        mock_service = MagicMock()
        mock_service.get_all_open_positions.return_value = mock_result
        mock_service_class.return_value = mock_service

        # First expire fails, second succeeds
        mock_wheel_svc = MagicMock()
        mock_wheel_svc.expire_trade.side_effect = [
            Exception("DB error"),
            MagicMock(),
        ]
        mock_wheel_svc_cls.return_value = mock_wheel_svc

        # Should not raise
        price_refresh_task()

        # Both should have been attempted
        assert mock_wheel_svc.expire_trade.call_count == 2
