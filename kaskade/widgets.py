from collections.abc import Mapping
from typing import Any, ClassVar

from rich.text import Text, TextType
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Container, Horizontal, ScrollableContainer
from textual.geometry import Size
from textual.widgets import DataTable, OptionList, Static
from textual.widgets._data_table import RowRenderables
from textual.widgets.data_table import CellType, ColumnKey

from kaskade import APP_NAME, APP_VERSION
from kaskade.configs import BOOTSTRAP_SERVERS


class KaskadeHeader(Horizontal):
    """Display the application version and active Kafka bootstrap servers."""

    def __init__(self, kafka_config: Mapping[str, Any], *, version: str = APP_VERSION) -> None:
        super().__init__(id="kaskade-header")
        bootstrap_servers = kafka_config.get(BOOTSTRAP_SERVERS, "Not configured")
        self.bootstrap_servers = str(bootstrap_servers).split(",", maxsplit=1)[0].strip()
        self.version = version

    def _product_text(self) -> Text:
        product = Text()
        product.append(APP_NAME.title(), style="primary")
        product.append(f" v{self.version}", style="secondary")
        return product

    def compose(self) -> ComposeResult:
        yield Static(
            self._product_text(),
            id="kaskade-product",
            markup=False,
        )
        yield Static(
            self.bootstrap_servers,
            id="kaskade-kafka",
            markup=False,
        )

    def on_mount(self) -> None:
        self.watch(self.app, "theme", self._refresh_product, init=False)

    def _refresh_product(self) -> None:
        self.query_one("#kaskade-product", Static).update(
            self._product_text(),
            layout=False,
        )


class TableFrame(Container):
    """Keep table borders and titles visible while table content is loading."""


class StretchyDataTable(DataTable[CellType]):
    """A data table whose columns can expand to fill the available width."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "enter",
            "select_cursor",
            "Select",
            show=False,
            tooltip="Select the highlighted row or cell.",
            id="kaskade.navigation.select",
        ),
        Binding(
            "up,k",
            "cursor_up",
            "Move Up",
            show=False,
            tooltip="Move the cursor up one row.",
            id="kaskade.navigation.up",
        ),
        Binding(
            "down,j",
            "cursor_down",
            "Move Down",
            show=False,
            tooltip="Move the cursor down one row.",
            id="kaskade.navigation.down",
        ),
        Binding(
            "left,h",
            "cursor_left",
            "Move Left",
            show=False,
            tooltip="Move the cursor or viewport left.",
            id="kaskade.navigation.left",
        ),
        Binding(
            "right,l",
            "cursor_right",
            "Move Right",
            show=False,
            tooltip="Move the cursor or viewport right.",
            id="kaskade.navigation.right",
        ),
        Binding(
            "pageup",
            "page_up",
            "Page Up",
            show=False,
            tooltip="Move the cursor up one page.",
            id="kaskade.navigation.page-up",
        ),
        Binding(
            "pagedown",
            "page_down",
            "Page Down",
            show=False,
            tooltip="Move the cursor down one page.",
            id="kaskade.navigation.page-down",
        ),
        Binding(
            "ctrl+pageup",
            "page_left",
            "Page Left",
            show=False,
            tooltip="Move the viewport left one page.",
            id="kaskade.navigation.page-left",
        ),
        Binding(
            "ctrl+pagedown",
            "page_right",
            "Page Right",
            show=False,
            tooltip="Move the viewport right one page.",
            id="kaskade.navigation.page-right",
        ),
        Binding(
            "ctrl+home,g",
            "scroll_top",
            "First Row",
            show=False,
            tooltip="Move to the first row.",
            id="kaskade.navigation.first",
        ),
        Binding(
            "ctrl+end,G",
            "scroll_bottom",
            "Last Row",
            show=False,
            tooltip="Move to the last row.",
            id="kaskade.navigation.last",
        ),
        Binding(
            "home",
            "scroll_home",
            "Row Start",
            show=False,
            tooltip="Move to the first visible column.",
            id="kaskade.navigation.home",
        ),
        Binding(
            "end",
            "scroll_end",
            "Row End",
            show=False,
            tooltip="Move to the last visible column.",
            id="kaskade.navigation.end",
        ),
    ]

    DEFAULT_CSS = """
    StretchyDataTable {
        scrollbar-gutter: stable;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._column_minimums: dict[ColumnKey, int] = {}
        self._column_stretches: dict[ColumnKey, int] = {}

    def _compute_row_renderables(self, row_index: int) -> RowRenderables:
        renderables = super()._compute_row_renderables(row_index)
        if row_index >= 0:
            for cell in renderables.cells:
                if isinstance(cell, Text) and cell.overflow is None:
                    cell.overflow = "ellipsis"
        return renderables

    def add_column(
        self,
        label: TextType,
        *,
        width: int | None = None,
        key: str | None = None,
        default: CellType | None = None,
        stretch: int = 0,
    ) -> ColumnKey:
        """Add a column, optionally assigning it a proportional stretch factor.

        The configured width is the column's minimum width. If omitted, the
        rendered label width is used as the minimum. Remaining table space is
        divided between columns according to their stretch factors.
        """
        if stretch < 0:
            raise ValueError("stretch must be greater than or equal to zero")

        column_key = super().add_column(label, width=width, key=key, default=default)
        column = self.columns[column_key]
        column.auto_width = False
        self._column_minimums[column_key] = column.width
        self._column_stretches[column_key] = stretch

        if self.is_mounted:
            self.call_after_refresh(self._stretch_columns)

        return column_key

    def on_resize(self, _event: events.Resize) -> None:
        self._stretch_columns()

    def _stretch_columns(self) -> None:
        columns = self.ordered_columns
        if not columns:
            return

        row_label_width = self._row_label_column_width
        available_width = max(0, self.scrollable_content_region.width - row_label_width)
        padding_width = 2 * self.cell_padding * len(columns)
        available_content_width = max(0, available_width - padding_width)

        minimums = [self._column_minimums[column.key] for column in columns]
        stretches = [self._column_stretches[column.key] for column in columns]
        extra_width = max(0, available_content_width - sum(minimums))
        total_stretch = sum(stretches)

        allocated_width = 0
        cumulative_stretch = 0
        for column, minimum, stretch in zip(columns, minimums, stretches):
            cumulative_stretch += stretch
            stretched_width = (
                extra_width * cumulative_stretch // total_stretch if total_stretch else 0
            )
            column.width = minimum + stretched_width - allocated_width
            allocated_width = stretched_width

        data_width = sum(column.get_render_width(self) for column in columns)
        self.virtual_size = Size(data_width + row_label_width, self.virtual_size.height)
        self.refresh()


class KaskadeOptionList(OptionList):
    """An option list with arrow and Vim-style navigation."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "down,j",
            "cursor_down",
            "Move Down",
            show=False,
            tooltip="Move to the next option.",
            id="kaskade.navigation.down",
        ),
        Binding(
            "up,k",
            "cursor_up",
            "Move Up",
            show=False,
            tooltip="Move to the previous option.",
            id="kaskade.navigation.up",
        ),
        Binding(
            "home,g",
            "first",
            "First Option",
            show=False,
            tooltip="Move to the first option.",
            id="kaskade.navigation.first",
        ),
        Binding(
            "end,G",
            "last",
            "Last Option",
            show=False,
            tooltip="Move to the last option.",
            id="kaskade.navigation.last",
        ),
        Binding(
            "pageup",
            "page_up",
            "Page Up",
            show=False,
            tooltip="Move up one page of options.",
            id="kaskade.navigation.page-up",
        ),
        Binding(
            "pagedown",
            "page_down",
            "Page Down",
            show=False,
            tooltip="Move down one page of options.",
            id="kaskade.navigation.page-down",
        ),
        Binding(
            "enter",
            "select",
            "Select",
            show=False,
            tooltip="Select the highlighted option.",
            id="kaskade.navigation.select",
        ),
    ]


class KaskadeScrollableContainer(ScrollableContainer):
    """A scrollable container with arrow and Vim-style navigation."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(
            "up,k",
            "scroll_up",
            "Scroll Up",
            show=False,
            tooltip="Scroll up one line.",
            id="kaskade.navigation.up",
        ),
        Binding(
            "down,j",
            "scroll_down",
            "Scroll Down",
            show=False,
            tooltip="Scroll down one line.",
            id="kaskade.navigation.down",
        ),
        Binding(
            "left,h",
            "scroll_left",
            "Scroll Left",
            show=False,
            tooltip="Scroll left one column.",
            id="kaskade.navigation.left",
        ),
        Binding(
            "right,l",
            "scroll_right",
            "Scroll Right",
            show=False,
            tooltip="Scroll right one column.",
            id="kaskade.navigation.right",
        ),
        Binding(
            "home,g",
            "scroll_home",
            "Scroll Home",
            show=False,
            tooltip="Scroll to the beginning.",
            id="kaskade.navigation.first",
        ),
        Binding(
            "end,G",
            "scroll_end",
            "Scroll End",
            show=False,
            tooltip="Scroll to the end.",
            id="kaskade.navigation.last",
        ),
        Binding(
            "pageup",
            "page_up",
            "Page Up",
            show=False,
            tooltip="Scroll up one page.",
            id="kaskade.navigation.page-up",
        ),
        Binding(
            "pagedown",
            "page_down",
            "Page Down",
            show=False,
            tooltip="Scroll down one page.",
            id="kaskade.navigation.page-down",
        ),
        Binding(
            "ctrl+pageup",
            "page_left",
            "Page Left",
            show=False,
            tooltip="Scroll left one page.",
            id="kaskade.navigation.page-left",
        ),
        Binding(
            "ctrl+pagedown",
            "page_right",
            "Page Right",
            show=False,
            tooltip="Scroll right one page.",
            id="kaskade.navigation.page-right",
        ),
    ]
