"""forge CLI entrypoint."""

from forge_cli.commands import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
