import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import DataTable

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
from kaskade.help import HelpableModalScreen, HelpScreen
from kaskade.keymaps import (
    KNOWN_BINDING_IDS,
)
from kaskade.models import Topic
from kaskade.settings import SETTINGS_ENV_VAR, default_settings_path, load_settings
from kaskade.themes import DEFAULT_THEME, KaskadeApp
from kaskade.widgets import KaskadeOptionList, KaskadeScrollableContainer, StretchyDataTable
from tests import configure_admin_service


class TestSettingsConfiguration(unittest.TestCase):
    def test_loads_settings(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text("admin:\n  refresh-interval: 10\n", encoding="utf-8")

            settings = load_settings(path)

        self.assertEqual(10, settings.admin_refresh_interval_seconds)

    def test_every_kaskade_binding_id_is_configurable(self):
        binding_owners = (
            KaskadeApp,
            HelpableModalScreen,
            HelpScreen,
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
        path = default_settings_path(
            environ={"XDG_CONFIG_HOME": "/tmp/xdg-config"},
            home=Path("/unused-home"),
        )

        self.assertEqual(Path("/tmp/xdg-config/kaskade/settings.yaml"), path)

    def test_falls_back_to_dot_config_on_linux_and_macos(self):
        path = default_settings_path(environ={}, home=Path("/users/kaskade"))

        self.assertEqual(Path("/users/kaskade/.config/kaskade/settings.yaml"), path)

    def test_explicit_settings_environment_variable_takes_precedence(self):
        path = default_settings_path(
            environ={
                SETTINGS_ENV_VAR: "/tmp/kaskade-settings.yaml",
                "XDG_CONFIG_HOME": "/tmp/xdg-config",
            },
            home=Path("/unused-home"),
        )

        self.assertEqual(Path("/tmp/kaskade-settings.yaml"), path)

    def test_missing_and_empty_files_use_defaults(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            missing = load_settings(directory / "missing.yaml")
            empty_path = directory / "empty.yaml"
            empty_path.write_text("", encoding="utf-8")
            empty = load_settings(empty_path)

        self.assertEqual({}, missing.keymap)
        self.assertIsNone(missing.theme)
        self.assertEqual((), missing.warnings)
        self.assertEqual({}, empty.keymap)
        self.assertIsNone(empty.theme)
        self.assertEqual((), empty.warnings)

    def test_loads_theme(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text("theme: dracula\n", encoding="utf-8")

            settings = load_settings(path)

        self.assertEqual("dracula", settings.theme)
        self.assertEqual((), settings.warnings)

    def test_invalid_theme_value_is_ignored_without_discarding_other_settings(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text(
                "theme: []\nadmin:\n  refresh-interval: 10\n",
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertIsNone(settings.theme)
        self.assertEqual(10, settings.admin_refresh_interval_seconds)
        self.assertEqual(1, len(settings.warnings))
        self.assertIn("non-empty string", settings.warnings[0])

    def test_loads_valid_binding_overrides(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text(
                """keymap:
  app.quit: ctrl+c
  kaskade.navigation.down: down,j
  kaskade.topics.filter: slash
""",
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual(
            {
                "app.quit": "ctrl+c",
                "kaskade.navigation.down": "down,j",
                "kaskade.topics.filter": "slash",
            },
            settings.keymap,
        )
        self.assertEqual((), settings.warnings)

    def test_loads_admin_refresh_interval(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text(
                "admin:\n  refresh-interval: 10\n",
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual(10, settings.admin_refresh_interval_seconds)
        self.assertEqual((), settings.warnings)

    def test_rejects_underscore_admin_setting_names(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text(
                "admin:\n  refresh_interval_seconds: 10\n",
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual(30, settings.admin_refresh_interval_seconds)
        self.assertEqual(1, len(settings.warnings))
        self.assertIn("admin.refresh_interval_seconds", settings.warnings[0])
        self.assertIn("hyphens, not underscores", settings.warnings[0])

    def test_disables_admin_refresh_with_zero(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text(
                "admin:\n  refresh-interval: 0\n",
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual(0, settings.admin_refresh_interval_seconds)

    def test_invalid_admin_refresh_uses_default_without_discarding_keymap(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text(
                """admin:
  refresh-interval: 2
keymap:
  app.quit: x
""",
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual(30, settings.admin_refresh_interval_seconds)
        self.assertEqual({"app.quit": "x"}, settings.keymap)
        self.assertEqual(1, len(settings.warnings))

    def test_ignores_invalid_entries_without_discarding_valid_ones(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text(
                """keymap:
  app.quit: x
  unknown.action: y
  help.toggle: ctrl+not_a_key
  kaskade.topics.filter: []
""",
                encoding="utf-8",
            )

            settings = load_settings(path)

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

            malformed = load_settings(malformed_path)
            list_document = load_settings(list_path)
            invalid_keymap = load_settings(invalid_keymap_path)

        self.assertEqual({}, malformed.keymap)
        self.assertEqual(1, len(malformed.warnings))
        self.assertEqual({}, list_document.keymap)
        self.assertEqual(1, len(list_document.warnings))
        self.assertEqual({}, invalid_keymap.keymap)
        self.assertEqual(1, len(invalid_keymap.warnings))


class TestConfiguredKeymap(unittest.IsolatedAsyncioTestCase):
    async def test_app_applies_configured_theme(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text("theme: dracula\n", encoding="utf-8")

            app = KaskadeApp(settings_path=path)

        self.assertEqual("dracula", app.theme)

    async def test_app_ignores_unknown_configured_theme(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text("theme: unknown\n", encoding="utf-8")

            app = KaskadeApp(settings_path=path)

        self.assertEqual(DEFAULT_THEME, app.theme)
        self.assertTrue(any("unknown theme" in warning for warning in app.settings.warnings))

    async def test_app_applies_configured_keymap(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text("keymap:\n  help.toggle: x,y\n", encoding="utf-8")
            app = KaskadeApp(settings_path=path)

            async with app.run_test() as pilot:
                await pilot.press("x")

                self.assertIsInstance(app.screen, HelpScreen)
                help_binding = next(
                    binding for binding in app.screen.help_bindings if binding.description == "Help"
                )
                self.assertEqual(("x", "y"), help_binding.keys)

                await pilot.press("x")
                self.assertNotIsInstance(app.screen, HelpScreen)

                await pilot.press("y")
                self.assertIsInstance(app.screen, HelpScreen)

    async def test_app_applies_navigation_override_to_child_widgets(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text("keymap:\n  kaskade.navigation.down: x\n", encoding="utf-8")

            with (
                patch.dict(os.environ, {SETTINGS_ENV_VAR: str(path)}),
                patch("kaskade.admin.TopicService") as topic_service,
            ):
                configure_admin_service(
                    topic_service.return_value,
                    {
                        "alpha": Topic(name="alpha"),
                        "bravo": Topic(name="bravo"),
                    },
                )
                app = KaskadeAdmin({})

                async with app.run_test() as pilot:
                    await pilot.pause()
                    table = app.query_one("#topics-table", DataTable)

                    await pilot.press("x")

                    self.assertEqual(1, table.cursor_row)

                    await pilot.press("?")
                    self.assertIsInstance(app.screen, HelpScreen)
                    move_down = next(
                        binding
                        for binding in app.screen.help_bindings
                        if binding.description == "Move Down"
                    )
                    self.assertEqual(("x",), move_down.keys)

    async def test_app_applies_copy_override_to_contextual_action(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "settings.yaml"
            path.write_text("keymap:\n  kaskade.topics.copy: x\n", encoding="utf-8")

            with (
                patch.dict(os.environ, {SETTINGS_ENV_VAR: str(path)}),
                patch("kaskade.admin.TopicService") as topic_service,
            ):
                configure_admin_service(
                    topic_service.return_value,
                    {"orders": Topic(name="orders")},
                )
                app = KaskadeAdmin({})

                async with app.run_test() as pilot:
                    await app.workers.wait_for_complete()
                    await pilot.pause()

                    await pilot.press("x")

                    self.assertEqual("orders", app.clipboard)

                    await pilot.press("?")
                    copy_topic = next(
                        binding
                        for binding in app.screen.help_bindings
                        if binding.description == "Copy Topic"
                    )
                    self.assertEqual(("x",), copy_topic.keys)
