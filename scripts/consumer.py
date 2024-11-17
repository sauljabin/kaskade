import click
from confluent_kafka import Consumer

from kaskade.configs import BOOTSTRAP_SERVERS, GROUP_ID, AUTO_OFFSET_RESET, EARLIEST
from scripts.sandbox import TOPICS


@click.command()
@click.option(
    "--bootstrap-servers", default="localhost:19092", help="Bootstrap servers.", show_default=True
)
def main(bootstrap_servers: str) -> None:
    consumer = Consumer(
        {
            BOOTSTRAP_SERVERS: bootstrap_servers,
            GROUP_ID: "sandbox.consumer",
            AUTO_OFFSET_RESET: EARLIEST,
        }
    )
    consumer.subscribe(
        [topic for topic, _, _ in TOPICS], on_assign=lambda a, b: print("Assignment completed")
    )

    while True:
        try:
            consumer.poll(timeout=1.0)
        except KeyboardInterrupt:
            break

    consumer.close()


if __name__ == "__main__":
    main()
