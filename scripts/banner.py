from textual.app import App, ComposeResult

from kaskade.colors import PRIMARY
from kaskade.widgets import KaskadeBanner


class Banner(App):
    DEFAULT_CSS = f"""
    KaskadeBanner{{
        width: 40;
        height: 8;
        border: double {PRIMARY};
        padding: 0 1 0 1;
    }}
    """

    def compose(self) -> ComposeResult:
        yield KaskadeBanner(include_slogan=True)


def main():
    app = Banner()
    app.run()


if __name__ == "__main__":
    main()
