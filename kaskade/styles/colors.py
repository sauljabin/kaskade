from textual.design import ColorSystem

PRIMARY = "#af5fd7"
SECONDARY = "#00af87"
DESIGN = {
    "dark": ColorSystem(
        primary=PRIMARY,
        secondary=SECONDARY,
        dark=True,
    ),
    "light": ColorSystem(
        primary=PRIMARY,
        secondary=SECONDARY,
        dark=False,
    ),
}
