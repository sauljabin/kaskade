"""The Kaskade admin application."""

from typing import Any

from textual.app import ComposeResult
from textual.timer import Timer
from textual.widgets import Footer

from kaskade.admin.topics import ListTopics
from kaskade.app import KaskadeApp
from kaskade.refresh import RefreshReason
from kaskade.timeouts import TimeoutConfig
from kaskade.topic_service import TopicService
from kaskade.widgets import KaskadeHeader, kantrip_profile


class KaskadeAdmin(KaskadeApp):
    TITLE = "Kaskade Admin"
    AUTO_FOCUS = "#topics-table"

    def __init__(
        self,
        kafka_config: dict[str, Any],
        refresh_interval: int | None = None,
        timeouts: TimeoutConfig | None = None,
    ):
        super().__init__()
        self.kafka_config = kafka_config
        self.timeouts = timeouts or TimeoutConfig()
        self.auto_refresh_interval = (
            self.settings.admin_refresh_interval_seconds
            if refresh_interval is None
            else refresh_interval
        )
        self._periodic_refresh_timer: Timer | None = None

    def on_mount(self) -> None:
        super().on_mount()
        if self.auto_refresh_interval:
            self._periodic_refresh_timer = self.set_interval(
                self.auto_refresh_interval,
                self._request_periodic_refresh,
                name="admin-auto-refresh",
                pause=True,
            )
        self.query_one(ListTopics).request_refresh(RefreshReason.INITIAL)

    def push_screen(self, *args: Any, **kwargs: Any) -> Any:
        self._pause_auto_refresh()
        return super().push_screen(*args, **kwargs)

    def pop_screen(self) -> Any:
        returning_to_topics = self._above_root_screen()
        result = super().pop_screen()
        if returning_to_topics:
            self.set_timer(0.1, self._resume_auto_refresh, name="resume-admin-auto-refresh")
        return result

    def _on_root_screen(self) -> bool:
        """Return whether the topic list is the active screen."""
        return len(self.screen_stack) == 1

    def _above_root_screen(self) -> bool:
        """Return whether a single screen covers the topic list."""
        return len(self.screen_stack) == 2

    def _pause_auto_refresh(self) -> None:
        if self._periodic_refresh_timer is not None:
            self._periodic_refresh_timer.pause()

    def _restart_auto_refresh(self) -> None:
        if self._periodic_refresh_timer is not None:
            self._periodic_refresh_timer.resume()
            self._periodic_refresh_timer.reset()

    def _resume_auto_refresh(self) -> None:
        if not self.auto_refresh_interval or not self._on_root_screen():
            return
        self._restart_auto_refresh()
        self.query_one(ListTopics).request_refresh(RefreshReason.RESUME)

    def _request_periodic_refresh(self) -> None:
        if self._on_root_screen():
            self.query_one(ListTopics).request_refresh(RefreshReason.PERIODIC)

    def on_list_topics_refresh_completed(self, _message: ListTopics.RefreshCompleted) -> None:
        if self._on_root_screen():
            self._restart_auto_refresh()

    def compose(self) -> ComposeResult:
        yield KaskadeHeader(self.kafka_config, profile=kantrip_profile())
        yield ListTopics(
            TopicService(
                self.kafka_config,
                timeouts=self.timeouts,
            ),
            refresh_interval=self.auto_refresh_interval,
        )
        yield Footer(compact=True)
