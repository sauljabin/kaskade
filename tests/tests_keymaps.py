import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from textual.widgets import DataTable, HelpPanel

from kaskade.admin import (
    CreateTopicScreen,
    DeleteTopicScreen,
    DescribeTopicScreen,
    EditTopicScreen,
    FilterTopicsScreen,
    KaskadeAdmin,
    ListTopics,
)
from kaskade.consumer import (
    ChunkSizeScreen,
    FilterRecordScreen,
    ListRecords,
    TopicScreen,
)
from kaskade.keymaps import CONFIG_ENV_VAR, KNOWN_BINDING_IDS, default_config_path, load_keymap
from kaskade.models import Topic
from kaskade.themes import KaskadeApp
from kaskade.widgets import KaskadeOptionList, KaskadeScrollableContainer, StretchyDataTable


class TestKeymapConfiguration(unittest.TestCase):
    def test_every_kaskade_binding_id_is_configurable(self):
        binding_owners = (
            KaskadeApp,
            FilterTopicsScreen,
            DeleteTopicScreen,
            DescribeTopicScreen,
            EditTopicScreen,
            CreateTopicScreen,
            ListTopics,
            FilterRecordScreen,
            ChunkSizeScreen,
            TopicScreen,
            ListRecords,
            StretchyDataTable,
            KaskadeOptionList,
            KaskadeScrollableContainer,
        )

        binding_ids = {
            binding.id
            for owner in binding_owners
            for binding in owner.BINDINGS
            if binding.id is not None
        }

        self.assertEqual(binding_ids, KNOWN_BINDING_IDS)

    def test_uses_xdg_config_home_on_linux_and_macos(self):
        path = default_config_path(
            environ={"XDG_CONFIG_HOME": "/tmp/xdg-config"},
            home=Path("/unused-home"),
        )

        self.assertEqual(Path("/tmp/xdg-config/kaskade/config.yaml"), path)

    def test_falls_back_to_dot_config_on_linux_and_macos(self):
        path = default_config_path(environ={}, home=Path("/users/kaskade"))

        self.assertEqual(Path("/users/kaskade/.config/kaskade/config.yaml"), path)

    def test_explicit_config_environment_variable_takes_precedence(self):
        path = default_config_path(
            environ={
                CONFIG_ENV_VAR: "/tmp/kaskade-keymap.yaml",
                "XDG_CONFIG_HOME": "/tmp/xdg-config",
            },
            home=Path("/unused-home"),
        )

        self.assertEqual(Path("/tmp/kaskade-keymap.yaml"), path)

    def test_missing_and_empty_files_use_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            missing = load_keymap(directory / "missing.yaml")
            empty_path = directory / "empty.yaml"
            empty_path.write_text("", encoding="utf-8")
            empty = load_keymap(empty_path)

        self.assertEqual({}, missing.keymap)
        self.assertEqual((), missing.warnings)
        self.assertEqual({}, empty.keymap)
        self.assertEqual((), empty.warnings)

    def test_loads_valid_binding_overrides(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.yaml"
            path.write_text(
                """keymap:
  app.quit: ctrl+c
  kaskade.navigation.down: down,j
  kaskade.topics.filter: slash
""",
                encoding="utf-8",
            )

            settings = load_keymap(path)

        self.assertEqual(
            {
                "app.quit": "ctrl+c",
                "kaskade.navigation.down": "down,j",
                "kaskade.topics.filter": "slash",
            },
            settings.keymap,
        )
        self.assertEqual((), settings.warnings)

    def test_ignores_invalid_entries_without_discarding_valid_ones(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.yaml"
            path.write_text(
                """keymap:
  app.quit: x
  unknown.action: y
  help.toggle: ctrl+not_a_key
  kaskade.topics.filter: []
""",
                encoding="utf-8",
            )

            settings = load_keymap(path)

        self.assertEqual({"app.quit": "x"}, settings.keymap)
        self.assertEqual(3, len(settings.warnings))
        self.assertTrue(any("unknown.action" in warning for warning in settings.warnings))
        self.assertTrue(any("ctrl+not_a_key" in warning for warning in settings.warnings))
        self.assertTrue(any("non-empty string" in warning for warning in settings.warnings))

    def test_malformed_documents_use_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            malformed_path = directory / "malformed.yaml"
            malformed_path.write_text("keymap: [", encoding="utf-8")
            list_path = directory / "list.yaml"
            list_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
            invalid_keymap_path = directory / "invalid-keymap.yaml"
            invalid_keymap_path.write_text("keymap: []\n", encoding="utf-8")

            malformed = load_keymap(malformed_path)
            list_document = load_keymap(list_path)
            invalid_keymap = load_keymap(invalid_keymap_path)

        self.assertEqual({}, malformed.keymap)
        self.assertEqual(1, len(malformed.warnings))
        self.assertEqual({}, list_document.keymap)
        self.assertEqual(1, len(list_document.warnings))
        self.assertEqual({}, invalid_keymap.keymap)
        self.assertEqual(1, len(invalid_keymap.warnings))


class TestConfiguredKeymap(unittest.IsolatedAsyncioTestCase):
    async def test_app_applies_configured_keymap(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.yaml"
            path.write_text("keymap:\n  help.toggle: x\n", encoding="utf-8")
            app = KaskadeApp(keymap_path=path)

            async with app.run_test() as pilot:
                await pilot.press("x")

                self.assertIsInstance(app.screen.query_one(HelpPanel), HelpPanel)

    async def test_app_applies_navigation_override_to_child_widgets(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.yaml"
            path.write_text("keymap:\n  kaskade.navigation.down: x\n", encoding="utf-8")

            with (
                patch.dict(os.environ, {CONFIG_ENV_VAR: str(path)}),
                patch("kaskade.admin.TopicService") as topic_service,
            ):
                topic_service.return_value.all = AsyncMock(
                    return_value={
                        "alpha": Topic(name="alpha"),
                        "bravo": Topic(name="bravo"),
                    }
                )
                app = KaskadeAdmin({})

                async with app.run_test() as pilot:
                    await pilot.pause()
                    table = app.query_one("#topics-table", DataTable)

                    await pilot.press("x")

                    self.assertEqual(1, table.cursor_row)
