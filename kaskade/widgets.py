from typing import Any

from rich.text import TextType
from textual import events
from textual.geometry import Size
from textual.widgets import DataTable
from textual.widgets.data_table import CellType, ColumnKey


class StretchyDataTable(DataTable[CellType]):
    """A data table whose columns can expand to fill the available width."""

    DEFAULT_CSS = """
    StretchyDataTable {
        scrollbar-gutter: stable;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._column_minimums: dict[ColumnKey, int] = {}
        self._column_stretches: dict[ColumnKey, int] = {}

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
