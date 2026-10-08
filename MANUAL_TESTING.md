# Manual Testing

The unit and E2E suites check what a program can check. These smoke tests cover
what needs a person: a real terminal, readable screens, and the full flow
against Kafka. Run them once per release candidate with the built wheel. They
take about 30 minutes.

Record the candidate commit, OS, terminal, and the result of each section. For a
failure, add the command and its sanitized output.

## 0. Setup

Install the candidate in isolation, so your own Kaskade stays untouched:

```bash
uv build --clear
pipx install --suffix=-qa dist/kaskade-*.whl
alias kaskade=kaskade-qa
```

Keep your own settings out of the test:

```bash
qa_tmp="${TMPDIR:-/tmp}"
export QA="$(mktemp -d "${qa_tmp%/}/kaskade-qa.XXXXXX")"
export KASKADE_SETTINGS="$QA/settings.yaml" XDG_STATE_HOME="$QA/state"
```

Start and populate the [sandbox](DEVELOPMENT.md#sandbox):

```bash
docker compose --project-directory sandbox up -d
uv run python -m sandbox
```

Clean up at the end:

```bash
docker compose --project-directory sandbox down -v
pipx uninstall kaskade-qa
rm -rf "$QA"
```

## 1. Command line

Each command must explain itself and reject bad input before opening the TUI.

```bash
kaskade --version
kaskade admin --help
kaskade consumer --help
kaskade producer --help
kaskade admin
kaskade admin --bootstrap-servers localhost:9092
kaskade producer -b localhost:9092 -t string --timeout consumer.poll=1
```

Expect:

- `--version` matches the candidate.
- Each `--help` lists only its own `--timeout` properties.
- `kaskade admin` without a broker says bootstrap servers are required.
- `--bootstrap-servers` is an unknown option.
- The producer rejects `consumer.poll` with `applies only to consumer`.

## 2. Admin

Admin must show the cluster and change topics safely.

```bash
kaskade admin -b localhost:9092
```

1. Check the topic list: partitions, replicas, records, and groups load after
   the names.
2. Press `?` for Help and `:` for Commands, then close each with `Esc`.
3. Press `/`, filter by `json`, and clear the filter with `Esc`.
4. Select a topic and press `d`. Check every tab in Topic Details.
5. Press `n` and create `qa-producer` with 3 partitions. It appears in the list.
6. Press `e` on `qa-producer` and raise it to 4 partitions.
7. Create `qa-delete`, then delete it with `Ctrl+D`; the dialog asks you to type
   the name.
8. Press `y` on a topic and paste: the topic name was copied.

Keep `qa-producer` for section 4.

## 3. Consumer

The consumer must decode every format and keep records readable.

Primitive and JSON formats:

```bash
kaskade consumer -b localhost:9092 --earliest -t string
kaskade consumer -b localhost:9092 --earliest -k string -v string -t null
kaskade consumer -b localhost:9092 --earliest -k string -v integer -t integer
kaskade consumer -b localhost:9092 --earliest -k string -v long -t long
kaskade consumer -b localhost:9092 --earliest -k string -v float -t float
kaskade consumer -b localhost:9092 --earliest -k string -v double -t double
kaskade consumer -b localhost:9092 --earliest -k string -v boolean -t boolean
kaskade consumer -b localhost:9092 --earliest -k string -v json -t json
kaskade consumer -b localhost:9092 --earliest -k string -v json -t json-schema \
    --json framing=confluent
```

Registry formats and failures:

```bash
kaskade consumer -b localhost:9092 --earliest -t avro-schema -k string -v registry \
    --registry url=http://localhost:8081
kaskade consumer -b localhost:9092 --earliest -t protobuf-schema -k string -v registry \
    --registry url=http://localhost:8081
kaskade consumer -b localhost:9092 --earliest -t avro-schema-apicurio -k string -v registry \
    --registry provider=apicurio \
    --registry apicurio.registry.url=http://localhost:8082/apis/registry/v3
kaskade consumer -b localhost:9092 --earliest -t errors -k registry -v registry \
    --fallback encoding=hex --registry url=http://localhost:8081
```

In any of them:

1. Records show decoded keys and values, not raw bytes. The `null` topic shows
   null key, value, and a `sandbox-null` header.
2. Press `Enter` for Record Details. Move with `n` and `N`, and check the Key,
   Value, and Headers tabs.
3. Press `y` to copy and `Ctrl+E` to export a record. The copy and the file are
   JSON.
4. Press `n` to consume more, `#` to change the chunk size, and `/` to filter.

In the `errors` topic, each malformed key, value, or header shows a warning and
falls back to hex, while the valid record decodes normally.

## 4. Producer

The producer must send exactly what you composed and claim delivery only after
the broker acknowledges it.

```bash
kaskade producer -b localhost:9092 -t qa-producer -v json
```

1. Go to **Headers** (`Tab`, then arrows). Press `n` to add `trace` = `a`, a
   second `trace` with **Null Value** checked, and `empty` with no value. Edit
   one with `e` and delete one with `Ctrl+D`. The order stays as entered.
2. In **Key**, type `order-1`. In **Value**, type `{"status": ` and check the
   status line: it reports invalid JSON. Press `Ctrl+S`; nothing is produced and
   the Value editor keeps focus.
3. Finish the value: `{"status": "paid"}`. **Preview** shows the topic,
   automatic partition, headers, serializers, and byte sizes.
4. Press `Ctrl+S`. The subtitle shows `Producing…`, then
   `Delivered · Partition … · Offset … · …`. The draft stays.
5. Check **Null** on the Value and produce a tombstone.
6. Quit with `Ctrl+C` and read the records back:

   ```bash
   kaskade consumer -b localhost:9092 --earliest -t qa-producer -k string -v json
   ```

   Both records are there with the headers in order, and the second value is
   null.

Source files:

```bash
printf '%s\n' \
    '{"key": {"content": "a"}, "value": {"content": {"n": 1}}}' \
    '{"headers": [{"key": "h", "value": null}], "value": {"content": {"n": 2}}}' \
    > "$QA/drafts.jsonl"
kaskade producer -b localhost:9092 -t qa-producer -v json --source "$QA/drafts.jsonl"
printf '%s\n' '{}' '[]' > "$QA/bad.jsonl"
kaskade producer -b localhost:9092 -t qa-producer --source "$QA/bad.jsonl"
```

Expect the title to show `Record 1/2`, `Ctrl+PageDown` and `Ctrl+PageUp` to move
between records without producing, and the bad file to fail with `Line 2`.

Failures:

```bash
kaskade producer -b localhost:9092 -t qa-producer --idempotence --acks 1
kaskade producer -b localhost:9092 -t qa-producer --partition 99
```

1. The first command fails before the TUI opens, saying `acks` must be `all`.
2. In the second, `Ctrl+S` shows `Delivery Error`. The draft stays and you can
   press `Ctrl+S` again.
3. Run `docker compose --project-directory sandbox stop kafka`, then produce
   with `--timeout producer.delivery=5`. After about 5 seconds the subtitle
   shows `Delivery Timeout`. `Ctrl+C` exits within a few seconds. Start the
   broker again with `docker compose --project-directory sandbox start kafka`.
4. The log never contains record content:

   ```bash
   ! grep -r -e order-1 -e paid "$XDG_STATE_HOME/kaskade" && echo "no content logged"
   ```

## 5. Themes and terminals

Every screen must stay readable in every theme and at any width.

```bash
kaskade producer -b localhost:9092 -t qa-producer --theme textual-light
kaskade consumer -b localhost:9092 --earliest -t json -v json --theme ansi-dark
kaskade admin -b localhost:9092 --theme eva01
```

1. Text, borders, and the Footer are readable in each theme.
2. Narrow the terminal below 80 columns. Modals, Help, and Commands fill the
   width, and the producer tabs and editors still fit.
3. Inside tmux or Zellij, `Ctrl+S`, `Ctrl+C`, `?`, and `:` behave the same.
