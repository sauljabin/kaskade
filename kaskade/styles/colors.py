from textual.design import ColorSystem

PRIMARY = "#af5fd7"
SECONDARY = "#87d7d7"
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
