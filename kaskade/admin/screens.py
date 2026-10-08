"""Topic filter, delete confirmation, and topic details screens."""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Grid
from textual.content import Content
from textual.widgets import DataTable, Footer, Input, TabbedContent, TabPane, Tabs

from kaskade.colors import PRIMARY
from kaskade.help import HelpableModalScreen, modal_bindings
from kaskade.models import MetricState, Topic, TopicConfiguration
from kaskade.ui import copy_text
from kaskade.unicodes import APPROXIMATION
from kaskade.widgets import MetadataCell, StretchyDataTable, TruncatedTooltipDataTable

BACK_SHORTCUT = "escape"
COPY_TOPIC_SHORTCUT = "y"
LOADING_METRIC = "…"
UNAVAILABLE_METRIC = "—"


def metric_value(state: MetricState, value: str) -> str:
    if state is MetricState.READY:
        return value
    if state is MetricState.UNAVAILABLE:
        return UNAVAILABLE_METRIC
    return LOADING_METRIC


class FilterTopicsScreen(HelpableModalScreen[str]):
    BINDING_GROUP_TITLE = "Filter Topics"
    AUTO_FOCUS = "#topic-filter"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            "enter",
            "apply_filter",
            "Apply Filter",
            priority=True,
            tooltip="Apply the topic name filter.",
            id="kaskade.filter-topics.apply",
        ),
        Binding(
            BACK_SHORTCUT,
            "close",
            "Back",
            tooltip="Close the filter without applying it.",
            id="kaskade.filter-topics.close",
        ),
    )

    def compose(self) -> ComposeResult:
        input_filter = Input(
            id="topic-filter", placeholder="Topic name contains…", classes="kaskade-input"
        )
        input_filter.border_title = f"[{PRIMARY}]Filter Topics[/]"
        yield input_filter
        yield Footer(compact=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_apply_filter(self) -> None:
        self.dismiss(self.query_one("#topic-filter", Input).value)

    def action_close(self) -> None:
        self.dismiss()


class DeleteTopicScreen(HelpableModalScreen[bool]):
    BINDING_GROUP_TITLE = "Delete Topic"
    AUTO_FOCUS = "#topic-confirmation"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            "enter",
            "delete",
            "Delete Topic",
            priority=True,
            tooltip="Delete the topic after its name has been confirmed.",
            id="kaskade.delete-topic.confirm",
        ),
        Binding(
            BACK_SHORTCUT,
            "cancel",
            "Cancel",
            tooltip="Keep the topic and close this confirmation.",
            id="kaskade.delete-topic.cancel",
        ),
    )

    def __init__(self, topic: Topic):
        super().__init__()
        self.topic = topic

    def compose(self) -> ComposeResult:
        label = Input(
            id="topic-confirmation",
            placeholder="Type the topic name to confirm",
            classes="kaskade-input",
        )
        label.border_title = rf"[{PRIMARY}]Delete Topic[/] \[[{PRIMARY}]{self.topic}[/]]"
        yield label
        yield Footer(compact=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._delete_if_confirmed(event.value)

    def action_delete(self) -> None:
        self._delete_if_confirmed(self.query_one("#topic-confirmation", Input).value)

    def _delete_if_confirmed(self, confirmation: str) -> None:
        if self.topic.name == confirmation:
            self.dismiss(True)
        else:
            self.notify(
                "Type the topic name exactly to confirm deletion",
                title="Confirmation Required",
                severity="warning",
            )

    def action_cancel(self) -> None:
        self.dismiss(False)


class DescribeTopicScreen(HelpableModalScreen):
    BINDING_GROUP_TITLE = "Topic Details"
    AUTO_FOCUS = "Tabs"
    HORIZONTAL_BREAKPOINTS = [  # noqa: RUF012
        (0, "-compact"),
        (50, "-narrow"),
        (80, "-wide"),
    ]
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            COPY_TOPIC_SHORTCUT,
            "copy_topic",
            "Copy Selection",
            show=False,
            tooltip="Copy the selected configuration or topic name to the clipboard.",
            id="kaskade.topics.copy",
        ),
        Binding(
            BACK_SHORTCUT,
            "close",
            "Back",
            tooltip="Close the topic details.",
            id="kaskade.describe-topic.close",
        ),
        Binding(
            "h",
            "previous_tab",
            "Previous Tab",
            show=False,
            tooltip="Show the previous topic detail tab.",
            id="kaskade.navigation.left",
        ),
        Binding(
            "l",
            "next_tab",
            "Next Tab",
            show=False,
            tooltip="Show the next topic detail tab.",
            id="kaskade.navigation.right",
        ),
    )

    def __init__(
        self,
        topic: Topic,
        configurations: tuple[TopicConfiguration, ...],
    ):
        super().__init__()
        self.topic = topic
        self.configurations = configurations

    def compose(self) -> ComposeResult:
        details = Container(classes="topic-details")
        details.border_title = rf"[{PRIMARY}]Topic Details[/] \[[{PRIMARY}]{self.topic.name}[/]]"
        with details:
            with Grid(id="topic-metadata"):
                for metadata_id, label, value in self._metadata():
                    yield MetadataCell(
                        label,
                        value,
                        id=metadata_id,
                        classes="topic-metadata-cell",
                    )
            with TabbedContent(initial="partitions", id="topic-details-tabs"):
                with TabPane(
                    Content(f"Partitions [{self.topic.partitions_count()}]"),
                    id="partitions",
                ):
                    yield self._partitions_table()
                with TabPane(
                    Content(f"Configurations [{len(self.configurations)}]"),
                    id="configurations",
                ):
                    yield self._configurations_table()
                with TabPane(Content(f"Groups [{self.topic.groups_count()}]"), id="groups"):
                    yield self._groups_table()
                with TabPane(
                    Content(f"Group Offsets [{self.topic.group_partitions_count()}]"),
                    id="group-offsets",
                ):
                    yield self._group_offsets_table()
                with TabPane(
                    Content(f"Group Members [{self.topic.group_members_count()}]"),
                    id="group-members",
                ):
                    yield self._group_members_table()
        yield Footer(compact=True)

    def _metadata(self) -> tuple[tuple[str, str, str], ...]:
        return (
            ("topic-partitions", "Partitions", str(self.topic.partitions_count())),
            ("topic-replicas", "Replicas", str(self.topic.replicas_count())),
            ("topic-isrs", "In Sync", str(self.topic.isrs_count())),
            (
                "topic-groups",
                "Groups",
                metric_value(self.topic.groups_state, str(self.topic.groups_count())),
            ),
            (
                "topic-members",
                "Members",
                metric_value(self.topic.groups_state, str(self.topic.group_members_count())),
            ),
            (
                "topic-records",
                "Records",
                metric_value(
                    self.topic.records_state,
                    f"{APPROXIMATION}{self.topic.records_count()}",
                ),
            ),
            (
                "topic-lag",
                "Lag",
                metric_value(self.topic.groups_state, f"{APPROXIMATION}{self.topic.lag()}"),
            ),
        )

    def _new_table(self, table_id: str) -> TruncatedTooltipDataTable[str]:
        table: TruncatedTooltipDataTable[str] = TruncatedTooltipDataTable(
            id=table_id, classes="details-table"
        )
        table.cursor_type = "row"
        return table

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        table = event.pane.query_one(StretchyDataTable)
        table.call_after_refresh(table.restretch)

    def _partitions_table(self) -> StretchyDataTable[str]:
        table = self._new_table("partitions-table")
        table.add_column("ID", stretch=1)
        table.add_column("Leader", stretch=1)
        table.add_column("Earliest", stretch=1)
        table.add_column("End", stretch=1)
        table.add_column("Records", stretch=1)
        table.add_column("ISRs", stretch=1)
        table.add_column("Replicas", stretch=1)

        for partition in self.topic.partitions:
            table.add_row(
                str(partition.id),
                str(partition.leader),
                metric_value(self.topic.records_state, str(partition.low)),
                metric_value(self.topic.records_state, str(partition.high)),
                metric_value(self.topic.records_state, str(partition.records_count())),
                str(partition.isrs),
                str(partition.replicas),
            )
        return table

    def _group_offsets_table(self) -> StretchyDataTable[str]:
        table = self._new_table("group-offsets-table")
        table.add_column("Group", width=18, stretch=3)
        table.add_column("Partition", stretch=1)
        table.add_column("Committed", stretch=1)
        table.add_column("End", stretch=1)
        table.add_column("Lag", stretch=1)

        for group in self.topic.groups:
            for partition in group.partitions:
                table.add_row(
                    group.id,
                    str(partition.id),
                    str(partition.offset),
                    metric_value(self.topic.records_state, str(partition.high)),
                    metric_value(self.topic.groups_state, str(partition.lag_count())),
                )
        return table

    def _configurations_table(self) -> StretchyDataTable[str]:
        table = self._new_table("configurations-table")
        table.add_column("Name", stretch=3)
        table.add_column("Value", stretch=2)

        for configuration in self._sorted_configurations():
            table.add_row(configuration.name, configuration.value)
        return table

    def _sorted_configurations(self) -> list[TopicConfiguration]:
        return sorted(self.configurations, key=lambda config: config.name.lower())

    def _groups_table(self) -> StretchyDataTable[str]:
        table = self._new_table("groups-table")
        table.add_column("ID", width=18, stretch=3)
        table.add_column("Coordinator", width=16, stretch=2)
        table.add_column("State", stretch=1)
        table.add_column("Assignor", stretch=1)
        table.add_column("Partitions", stretch=1)
        table.add_column("Members", stretch=1)
        table.add_column("Lag", stretch=1)

        for group in self.topic.groups:
            table.add_row(
                group.id,
                str(group.coordinator) if group.coordinator else "",
                group.state,
                group.partition_assignor,
                str(group.partitions_count()),
                str(group.members_count()),
                str(group.lag_count()),
            )
        return table

    def _group_members_table(self) -> StretchyDataTable[str]:
        table = self._new_table("group-members-table")
        table.add_column("Group", stretch=2)
        table.add_column("Client ID", stretch=2)
        table.add_column("Member ID", stretch=3)
        table.add_column("Host", stretch=2)
        table.add_column("Assignment")

        for group in self.topic.groups:
            for member in group.members:
                table.add_row(
                    member.group,
                    member.client_id,
                    member.id,
                    member.host,
                    str(member.assignment),
                )
        return table

    def action_close(self) -> None:
        self.dismiss()

    def action_copy_topic(self) -> None:
        if self.query_one(TabbedContent).active == "configurations":
            table = self.query_one("#configurations-table", DataTable)
            if table.row_count == 0:
                return
            configuration = self._sorted_configurations()[table.cursor_row]
            copy_text(
                self.app,
                f"{configuration.name}={configuration.value}",
                "configuration",
            )
            return
        copy_text(self.app, self.topic.name, "topic name")

    def action_previous_tab(self) -> None:
        self.query_one(Tabs).action_previous_tab()

    def action_next_tab(self) -> None:
        self.query_one(Tabs).action_next_tab()
