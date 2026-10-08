"""The shared topic form behind the create and edit topic screens."""

from collections.abc import Iterator, Mapping
from typing import ClassVar, TypeVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container
from textual.validation import Function, Integer, Validator
from textual.widget import Widget
from textual.widgets import Collapsible, Footer, Input, RadioButton, RadioSet

from kaskade.admin.screens import BACK_SHORTCUT
from kaskade.colors import PRIMARY
from kaskade.commands import CreateTopicCommand, UpdateTopicCommand
from kaskade.configs import (
    CLEANUP_POLICY_CONFIG,
    MILLISECONDS_1W,
    MIN_INSYNC_REPLICAS_CONFIG,
    RETENTION_MS_CONFIG,
)
from kaskade.help import HelpableModalScreen, modal_bindings
from kaskade.models import CleanupPolicy, Topic

SAVE_SHORTCUT = "ctrl+s,ctrl+shift+s,f2"
ADVANCED_ID = "advanced-topic-config"
FIELD_LABELS = {
    "name": "Name",
    "partitions": "Partitions",
    "replicas": "Replication Factor",
    "min_insync_replicas": "Min In-Sync Replicas",
    "retention": "Retention",
}
"""Input IDs and their labels in validation and focus order."""

FormResult = TypeVar("FormResult")


def _valid_topic_name(name: str) -> bool:
    return (
        0 < len(name) <= 249
        and name not in {".", ".."}
        and all(
            character.isascii() and (character.isalnum() or character in "._-")
            for character in name
        )
    )


def _valid_optional_positive_integer(value: str) -> bool:
    return not value or (value.isdigit() and int(value) >= 1)


def _optional_positive_integer(description: str) -> Function:
    return Function(_valid_optional_positive_integer, description)


def _optional_int(value: str) -> int | None:
    return int(value) if value else None


def _input(
    input_id: str,
    title: str,
    validator: Validator,
    *,
    value: str = "",
    placeholder: str = "",
    integer: bool = True,
) -> Input:
    input_widget = Input(
        id=input_id,
        type="integer" if integer else "text",
        value=value,
        placeholder=placeholder,
        validators=validator,
        classes="kaskade-input",
    )
    input_widget.border_title = title
    return input_widget


class CleanupPolicyButton(RadioButton):
    """A radio button that carries the cleanup policy it selects."""

    def __init__(self, policy: CleanupPolicy, *, value: bool) -> None:
        super().__init__(str(policy), value=value)
        self.policy = policy


class TopicFormScreen(HelpableModalScreen[FormResult]):
    """Partitions, retention, cleanup policy, and advanced replication inputs.

    Subclasses add their own inputs, validation, and result.
    """

    EMPTY_MIN_INSYNC_DESCRIPTION: ClassVar[str]
    MIN_INSYNC_PLACEHOLDER: ClassVar[str] = ""

    def __init__(
        self,
        *,
        partitions: int,
        retention: str,
        cleanup_policy: str,
        min_insync_replicas: str,
    ) -> None:
        super().__init__()
        self.initial_partitions = partitions
        self.initial_retention = retention
        self.initial_cleanup_policy = cleanup_policy
        self.initial_min_insync_replicas = min_insync_replicas

    def compose(self) -> ComposeResult:
        container = Container(classes="topic-form")
        container.border_title = self.form_title()
        with container:
            yield from self.leading_inputs()
            yield _input(
                "partitions",
                "Partitions",
                Integer(minimum=self.initial_partitions),
                value=str(self.initial_partitions),
            )
            yield _input(
                "retention",
                "Retention (ms)",
                Integer(minimum=-1),
                value=self.initial_retention,
            )
            with RadioSet(id="cleanup", classes="kaskade-radio") as radio_set:
                radio_set.border_title = "Cleanup Policy"
                for policy in (CleanupPolicy.DELETE, CleanupPolicy.COMPACT):
                    yield CleanupPolicyButton(
                        policy, value=str(policy) == self.initial_cleanup_policy
                    )
            with Collapsible(title="Advanced", id=ADVANCED_ID):
                yield from self.advanced_inputs()
                yield _input(
                    "min_insync_replicas",
                    "Min In-Sync Replicas",
                    (
                        Integer(minimum=1)
                        if self.initial_min_insync_replicas
                        else _optional_positive_integer(self.EMPTY_MIN_INSYNC_DESCRIPTION)
                    ),
                    value=self.initial_min_insync_replicas,
                    placeholder=self.MIN_INSYNC_PLACEHOLDER,
                )
        yield Footer(compact=True)

    def form_title(self) -> str:
        return f"[{PRIMARY}]{self.BINDING_GROUP_TITLE}[/]"

    def leading_inputs(self) -> Iterator[Widget]:
        yield from ()

    def advanced_inputs(self) -> Iterator[Widget]:
        yield from ()

    def cross_field_failures(self, inputs: Mapping[str, Input]) -> list[str]:
        """Return failures that depend on several valid inputs."""
        return []

    def labelled_inputs(self) -> dict[str, Input]:
        inputs = {input_widget.id: input_widget for input_widget in self.query(Input)}
        return {
            label: inputs[input_id]
            for input_id, label in FIELD_LABELS.items()
            if input_id in inputs
        }

    def validated_inputs(self) -> dict[str, Input] | None:
        """Return the inputs by label, or reveal and report the invalid ones."""
        inputs = self.labelled_inputs()
        failures: list[str] = []
        for label, input_widget in inputs.items():
            result = input_widget.validate(input_widget.value)
            if result is not None and not result.is_valid:
                description = result.failure_descriptions[0].removesuffix(".")
                failures.append(f"{label}: {description}")
        if not failures:
            failures = self.cross_field_failures(inputs)
        if not failures:
            return inputs

        advanced = self.query_one(f"#{ADVANCED_ID}", Collapsible)
        if advanced.query("Input.-invalid"):
            advanced.collapsed = False
        next(
            input_widget for input_widget in inputs.values() if input_widget.has_class("-invalid")
        ).focus()
        self.notify("\n".join(failures), title="Invalid Topic", severity="warning")
        return None

    def selected_cleanup_policy(self) -> CleanupPolicy | None:
        pressed_button = self.query_one("#cleanup", RadioSet).pressed_button
        return pressed_button.policy if isinstance(pressed_button, CleanupPolicyButton) else None

    def action_back(self) -> None:
        self.dismiss()


class CreateTopicScreen(TopicFormScreen[CreateTopicCommand]):
    BINDING_GROUP_TITLE = "Create Topic"
    AUTO_FOCUS = "#name"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            SAVE_SHORTCUT,
            "create",
            "Create Topic",
            tooltip="Create the topic with the configured values.",
            id="kaskade.create-topic.save",
        ),
        Binding(
            BACK_SHORTCUT,
            "back",
            "Back",
            tooltip="Close the form without creating a topic.",
            id="kaskade.create-topic.close",
        ),
    )
    EMPTY_MIN_INSYNC_DESCRIPTION = (
        "Enter a positive integer or leave empty to use the broker default"
    )
    MIN_INSYNC_PLACEHOLDER = "Broker default"

    def __init__(self) -> None:
        super().__init__(
            partitions=1,
            retention=str(MILLISECONDS_1W),
            cleanup_policy=str(CleanupPolicy.DELETE),
            min_insync_replicas="",
        )

    def leading_inputs(self) -> Iterator[Widget]:
        yield _input(
            "name",
            "Name",
            Function(
                _valid_topic_name,
                "Enter a name up to 249 characters using letters, numbers, dots, underscores, "
                "or hyphens. The name can't be empty or consist only of one or two dots",
            ),
            placeholder="Letters, numbers, '.', '_' and '-'",
            integer=False,
        )

    def advanced_inputs(self) -> Iterator[Widget]:
        yield _input(
            "replicas",
            "Replication Factor",
            _optional_positive_integer(self.EMPTY_MIN_INSYNC_DESCRIPTION),
            placeholder=self.MIN_INSYNC_PLACEHOLDER,
        )

    def cross_field_failures(self, inputs: Mapping[str, Input]) -> list[str]:
        replicas = _optional_int(inputs["Replication Factor"].value)
        min_insync_input = inputs["Min In-Sync Replicas"]
        min_insync_replicas = _optional_int(min_insync_input.value)
        if replicas is None or min_insync_replicas is None or min_insync_replicas <= replicas:
            return []
        min_insync_input.add_class("-invalid")
        return ["Min In-Sync Replicas cannot exceed Replication Factor"]

    def action_create(self) -> None:
        inputs = self.validated_inputs()
        if inputs is None:
            return
        self.dismiss(
            CreateTopicCommand(
                name=inputs["Name"].value,
                partitions=int(inputs["Partitions"].value),
                replicas=_optional_int(inputs["Replication Factor"].value),
                min_insync_replicas=_optional_int(inputs["Min In-Sync Replicas"].value),
                cleanup_policy=str(self.selected_cleanup_policy() or CleanupPolicy.DELETE),
                retention_ms=int(inputs["Retention"].value),
            )
        )


class EditTopicScreen(TopicFormScreen[UpdateTopicCommand]):
    BINDING_GROUP_TITLE = "Edit Topic"
    AUTO_FOCUS = "#partitions"
    BINDINGS: ClassVar[list[BindingType]] = modal_bindings(
        Binding(
            SAVE_SHORTCUT,
            "edit",
            "Save Changes",
            tooltip="Apply the edited Kafka topic configuration.",
            id="kaskade.edit-topic.save",
        ),
        Binding(
            BACK_SHORTCUT,
            "back",
            "Back",
            tooltip="Close the editor without saving changes.",
            id="kaskade.edit-topic.close",
        ),
    )
    EMPTY_MIN_INSYNC_DESCRIPTION = "Enter a positive integer or leave empty when unavailable"

    def __init__(self, topic: Topic, configs: Mapping[str, str]) -> None:
        super().__init__(
            partitions=topic.partitions_count(),
            retention=configs.get(RETENTION_MS_CONFIG) or "",
            cleanup_policy=configs.get(CLEANUP_POLICY_CONFIG) or "",
            min_insync_replicas=configs.get(MIN_INSYNC_REPLICAS_CONFIG) or "",
        )
        self.topic = topic

    def form_title(self) -> str:
        return rf"{super().form_title()} \[[{PRIMARY}]{self.topic.name}[/]]"

    def action_edit(self) -> None:
        inputs = self.validated_inputs()
        if inputs is None:
            return
        self.dismiss(
            UpdateTopicCommand(
                partitions=int(inputs["Partitions"].value),
                min_insync_replicas=self._changed_min_insync_replicas(
                    inputs["Min In-Sync Replicas"].value
                ),
                cleanup_policy=self._changed_cleanup_policy(),
                retention_ms=self._changed_retention_ms(inputs["Retention"].value),
            )
        )

    def _changed_min_insync_replicas(self, value: str) -> int | None:
        min_insync_replicas = _optional_int(value)
        if min_insync_replicas == _optional_int(self.initial_min_insync_replicas):
            return None
        return min_insync_replicas

    def _changed_cleanup_policy(self) -> str | None:
        selected = self.selected_cleanup_policy()
        if selected is None or str(selected) == self.initial_cleanup_policy:
            return None
        return str(selected)

    def _changed_retention_ms(self, value: str) -> int | None:
        retention_ms = int(value)
        return None if retention_ms == _optional_int(self.initial_retention) else retention_ms
