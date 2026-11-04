"""Topic filter, review, delete confirmation, and topic details screens."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Grid
from textual.content import Content
from textual.widgets import DataTable, Footer, Input, TabbedContent, TabPane, Tabs

from kaskade.colors import PRIMARY
from kaskade.commands import UpdateTopicCommand
from kaskade.group_service import OffsetResetPlan
from kaskade.help import HelpableModalScreen, modal_bindings
from kaskade.models import MetricState, Topic, TopicConfiguration
from kaskade.ui import copy_text
from kaskade.unicodes import APPROXIMATION
from kaskade.widgets import MetadataCell, StretchyDataTable, TruncatedTooltipDataTable

BACK_SHORTCUT = "escape"
SAVE_SHORTCUT = "ctrl+s,ctrl+shift+s,f2"
CLUSTER_DEFAULT = "Cluster default"
COPY_TOPIC_SHORTCUT = "y"
RESET_OFFSETS_SHORTCUT = "r"
DELETE_GROUP_SHORTCUT = "ctrl+d"
GROUP_ACTIONS = frozenset({"reset_offsets", "delete_group"})
"""Topic Details actions that change a consumer group, which read-only mode refuses."""
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


class ReviewTopicChangesScreen(HelpableModalScreen[bool]):
    """List an edit's changes, each with its current and new value, before applying it."""

    BINDING_GROUP_TITLE = "Review Changes"
    AUTO_FOCUS = "#topic-changes"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            SAVE_SHORTCUT,
            "apply",
            "Apply Changes",
            tooltip="Apply the listed changes to the topic.",
            id="kaskade.review-topic-changes.apply",
        ),
        Binding(
            BACK_SHORTCUT,
            "back",
            "Back",
            tooltip="Return to the editor without applying the changes.",
            id="kaskade.review-topic-changes.close",
        ),
    )

    def __init__(self, topic: Topic, command: UpdateTopicCommand):
        super().__init__()
        self.topic = topic
        self.command = command

    def compose(self) -> ComposeResult:
        review = Container(classes="topic-review")
        review.border_title = rf"[{PRIMARY}]Review Changes[/] \[[{PRIMARY}]{self.topic.name}[/]]"
        with review:
            table: TruncatedTooltipDataTable[str] = TruncatedTooltipDataTable(
                id="topic-changes", classes="details-table"
            )
            table.cursor_type = "row"
            rows = self.change_rows()
            table.add_column("Setting", width=max(len(row[0]) for row in rows), stretch=3)
            table.add_column("Change", width=max(len(row[1]) for row in rows), stretch=1)
            table.add_column("Current", stretch=2)
            table.add_column("New", width=len(CLUSTER_DEFAULT), stretch=2)
            for row in rows:
                table.add_row(*row)
            yield table
        yield Footer(compact=True)

    def change_rows(self) -> list[tuple[str, str, str, str]]:
        """Return each change as its setting, kind, current value, and new value."""
        rows: list[tuple[str, str, str, str]] = []
        if self.command.partitions is not None:
            rows.append(
                (
                    "Partitions",
                    "Increase",
                    str(self.topic.partitions_count()),
                    str(self.command.partitions),
                )
            )
        for change in self.command.configs:
            if change.value is None:
                rows.append((change.name, "Reset", change.current, CLUSTER_DEFAULT))
            else:
                rows.append((change.name, "Set", change.current, change.value))
        return rows

    def action_apply(self) -> None:
        self.dismiss(True)

    def action_back(self) -> None:
        self.dismiss(False)


class ConfirmDeletionScreen(HelpableModalScreen[bool]):
    """Confirm a deletion by typing the exact name of what it deletes."""

    INPUT_ID: ClassVar[str]
    NOUN: ClassVar[str]
    WARNING: ClassVar[str] = ""

    def __init__(self, name: str):
        super().__init__()
        self.name_to_confirm = name

    def compose(self) -> ComposeResult:
        confirmation = Input(
            id=self.INPUT_ID,
            placeholder=f"Type the {self.NOUN} to confirm",
            classes="kaskade-input",
        )
        confirmation.border_title = (
            rf"[{PRIMARY}]{self.BINDING_GROUP_TITLE}[/] \[[{PRIMARY}]{self.name_to_confirm}[/]]"
        )
        confirmation.border_subtitle = self.WARNING
        yield confirmation
        yield Footer(compact=True)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._delete_if_confirmed(event.value)

    def action_delete(self) -> None:
        self._delete_if_confirmed(self.query_one(f"#{self.INPUT_ID}", Input).value)

    def _delete_if_confirmed(self, confirmation: str) -> None:
        if self.name_to_confirm == confirmation:
            self.dismiss(True)
        else:
            self.notify(
                f"Type the {self.NOUN} exactly to confirm deletion",
                title="Confirmation Required",
                severity="warning",
            )

    def action_cancel(self) -> None:
        self.dismiss(False)


class DeleteTopicScreen(ConfirmDeletionScreen):
    BINDING_GROUP_TITLE = "Delete Topic"
    AUTO_FOCUS = "#topic-confirmation"
    INPUT_ID = "topic-confirmation"
    NOUN = "topic name"
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
        super().__init__(topic.name)
        self.topic = topic


class DeleteGroupScreen(ConfirmDeletionScreen):
    BINDING_GROUP_TITLE = "Delete Group"
    AUTO_FOCUS = "#group-confirmation"
    INPUT_ID = "group-confirmation"
    NOUN = "group ID"
    WARNING = "Deletes its offsets for every topic"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            "enter",
            "delete",
            "Delete Group",
            priority=True,
            tooltip="Delete the consumer group after its ID has been confirmed.",
            id="kaskade.delete-group.confirm",
        ),
        Binding(
            BACK_SHORTCUT,
            "cancel",
            "Cancel",
            tooltip="Keep the consumer group and close this confirmation.",
            id="kaskade.delete-group.cancel",
        ),
    )


class ReviewOffsetResetScreen(HelpableModalScreen[bool]):
    """List each partition's current and new committed offset before resetting them."""

    BINDING_GROUP_TITLE = "Review Reset"
    AUTO_FOCUS = "#offset-resets"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            SAVE_SHORTCUT,
            "apply",
            "Apply Reset",
            tooltip="Commit the listed offsets for the consumer group.",
            id="kaskade.review-offset-reset.apply",
        ),
        Binding(
            BACK_SHORTCUT,
            "back",
            "Back",
            tooltip="Return to the reset form without committing offsets.",
            id="kaskade.review-offset-reset.close",
        ),
    )

    def __init__(self, plan: OffsetResetPlan):
        super().__init__()
        self.plan = plan

    def compose(self) -> ComposeResult:
        review = Container(classes="topic-review")
        review.border_title = rf"[{PRIMARY}]Review Reset[/] \[[{PRIMARY}]{self.plan.group}[/]]"
        review.border_subtitle = f"Topic {self.plan.topic}"
        with review:
            table: TruncatedTooltipDataTable[str] = TruncatedTooltipDataTable(
                id="offset-resets", classes="details-table"
            )
            table.cursor_type = "row"
            table.add_column("Partition", stretch=1)
            table.add_column("Current", stretch=2)
            table.add_column("New", stretch=2)
            for reset in self.plan.resets:
                table.add_row(
                    str(reset.partition),
                    UNAVAILABLE_METRIC if reset.current is None else str(reset.current),
                    str(reset.new),
                )
            yield table
        yield Footer(compact=True)

    def action_apply(self) -> None:
        self.dismiss(True)

    def action_back(self) -> None:
        self.dismiss(False)


class GroupActionKind(Enum):
    RESET_OFFSETS = auto()
    DELETE = auto()


@dataclass(frozen=True)
class GroupAction:
    """A consumer group action chosen in Topic Details, with the selected partition."""

    kind: GroupActionKind
    group: str
    partition: int | None = None


GROUP_TABS = frozenset({"groups", "group-offsets"})
"""Topic Details tabs whose selected row names a consumer group."""


class DescribeTopicScreen(HelpableModalScreen[GroupAction]):
    BINDING_GROUP_TITLE = "Topic Details"
    AUTO_FOCUS = "Tabs"
    HORIZONTAL_BREAKPOINTS = [  # noqa: RUF012
        (0, "-compact"),
        (50, "-narrow"),
        (80, "-wide"),
    ]
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            RESET_OFFSETS_SHORTCUT,
            "reset_offsets",
            "Reset Offsets",
            tooltip="Reset the selected consumer group's committed offsets for this topic.",
            id="kaskade.describe-topic.reset-offsets",
        ),
        Binding(
            DELETE_GROUP_SHORTCUT,
            "delete_group",
            "Delete Group",
            tooltip="Delete the selected consumer group and its offsets for every topic.",
            id="kaskade.describe-topic.delete-group",
        ),
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
        *,
        read_only: bool = False,
    ):
        super().__init__()
        self.topic = topic
        self.configurations = configurations
        self.read_only = read_only

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

    def on_tabbed_content_tab_activated(self, _event: TabbedContent.TabActivated) -> None:
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Offer group actions only on a group tab with a selected group."""
        if action in GROUP_ACTIONS:
            return not self.read_only and self.selected_group() is not None
        return True

    def selected_group(self) -> tuple[str, int | None] | None:
        """Return the selected group and, on Group Offsets, its partition."""
        active = self.query_one(TabbedContent).active
        if active not in GROUP_TABS:
            return None
        table = self.query_one(f"#{active}-table", DataTable)
        if table.row_count == 0:
            return None
        if active == "groups":
            return self.topic.groups[table.cursor_row].id, None
        group, partition = self._group_offset_rows()[table.cursor_row]
        return group, partition

    def _group_offset_rows(self) -> list[tuple[str, int]]:
        return [
            (group.id, partition.id)
            for group in self.topic.groups
            for partition in group.partitions
        ]

    def action_reset_offsets(self) -> None:
        self._dismiss_with(GroupActionKind.RESET_OFFSETS)

    def action_delete_group(self) -> None:
        self._dismiss_with(GroupActionKind.DELETE)

    def _dismiss_with(self, kind: GroupActionKind) -> None:
        selected = self.selected_group()
        if selected is not None:
            group, partition = selected
            self.dismiss(GroupAction(kind, group, partition))

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
