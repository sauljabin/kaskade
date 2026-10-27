"use strict";

// Progressive enhancement only: without this script the page shows the
// consumer's final screen and the install commands as plain text.

function setUpCopyButtons() {
  const status = document.querySelector(".copy-status");
  if (!status || !navigator.clipboard) return;
  for (const button of document.querySelectorAll("[data-copy]")) {
    const source = document.getElementById(button.dataset.copy);
    if (!source) continue;
    button.hidden = false;
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(source.textContent);
        status.textContent = `Copied ${source.textContent}`;
      } catch {
        status.textContent = "Copy failed; select the command instead";
      }
    });
  }
}

async function loadRelease() {
  const line = document.querySelector("[data-release]");
  if (!line) return;
  try {
    const response = await fetch(
      "https://api.github.com/repos/sauljabin/kaskade/releases/latest",
      { headers: { Accept: "application/vnd.github+json" } },
    );
    if (!response.ok) return;
    const release = await response.json();
    if (typeof release.tag_name !== "string" || !release.tag_name) return;
    const link = line.querySelector("a");
    link.textContent = release.tag_name;
    link.href = `${link.href}/tag/${encodeURIComponent(release.tag_name)}`;
    line.dataset.state = "stable";
    for (const version of document.querySelectorAll("[data-version]")) {
      version.textContent = release.tag_name;
    }
  } catch {
    // Offline or rate limited: keep the link to the Releases page.
  }
}

// Indented JSON with the classes Kaskade's Rich styles map to.
function highlightJson(text) {
  const fragment = document.createDocumentFragment();
  const json = JSON.stringify(JSON.parse(text), null, 2);
  const token = /("(?:[^"\\]|\\.)*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;
  let last = 0;
  for (const match of json.matchAll(token)) {
    fragment.append(json.slice(last, match.index));
    const span = document.createElement("span");
    span.className = match[2] ? "j-key" : match[1] ? "j-string" : "j-number";
    span.textContent = match[1] ?? match[3];
    fragment.append(span, match[2] ?? "");
    last = match.index + match[0].length;
  }
  fragment.append(json.slice(last));
  return fragment;
}

// Replays a consumer session over the static final screen: type the command,
// receive the records, move down two rows, and open Record Details.
function setUpDemo() {
  const demo = document.querySelector("[data-demo]");
  const controls = document.querySelector(".demo-controls");
  if (!demo || !controls || !("IntersectionObserver" in window)) return;
  const screen = demo.querySelector(".screen");
  const command = demo.querySelector("[data-shell-command]");
  const typed = command.textContent;
  const count = demo.querySelector("[data-count]");
  const rows = [...demo.querySelectorAll("[data-records] tr")];
  const details = demo.querySelector("[data-details]");
  const keycap = demo.querySelector("[data-keycap]");
  const toggle = controls.querySelector("[data-demo-toggle]");
  const replay = controls.querySelector("[data-demo-replay]");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

  let queue = [];
  let index = 0;
  let timer = 0;
  let due = 0;
  let remaining = 0;
  let state = "idle";

  function select(position) {
    rows.forEach((row, rowIndex) => row.classList.toggle("selected", rowIndex === position));
    return rows[position];
  }

  function press(key) {
    keycap.textContent = key;
    keycap.hidden = false;
  }

  function showDetails(row) {
    const [key, value, size, timestamp, partition, offset] = [...row.cells].map(
      (cell) => cell.textContent,
    );
    const fields = {
      size,
      timestamp,
      partition,
      offset,
      "value-size": `${new TextEncoder().encode(value).length} bytes`,
    };
    for (const field of details.querySelectorAll("[data-detail]")) {
      const name = field.dataset.detail;
      if (name === "value") field.replaceChildren(highlightJson(value));
      else field.textContent = fields[name];
    }
    details.setAttribute("aria-label", `Record Details for ${key}`);
    details.hidden = false;
  }

  function reset() {
    screen.dataset.view = "shell";
    command.textContent = "";
    rows.forEach((row) => {
      row.hidden = true;
    });
    count.textContent = "0";
    select(0);
    details.hidden = true;
    keycap.hidden = true;
  }

  function buildQueue() {
    const steps = [];
    const at = (delay, action) => steps.push([delay, action]);
    for (const character of typed) {
      at(character === " " ? 70 : 35, () => command.append(character));
    }
    at(450, () => press("⏎"));
    at(400, () => {
      keycap.hidden = true;
      screen.dataset.view = "tui";
    });
    rows.forEach((row, rowIndex) => {
      at(rowIndex ? 140 : 700, () => {
        row.hidden = false;
        count.textContent = String(rowIndex + 1);
      });
    });
    at(1200, () => press("j"));
    at(150, () => select(1));
    at(550, () => press("j"));
    at(150, () => select(2));
    at(800, () => press("⏎"));
    at(150, () => showDetails(rows[2]));
    at(3600, () => press("esc"));
    at(150, () => {
      details.hidden = true;
    });
    at(900, finish);
    return steps;
  }

  function tick() {
    const [, action] = queue[index];
    index += 1;
    action();
    if (state === "playing") schedule(queue[index][0]);
  }

  function schedule(delay) {
    due = performance.now() + delay;
    timer = window.setTimeout(tick, delay);
  }

  function render() {
    toggle.textContent = state === "paused" ? "Resume" : "Pause";
    toggle.disabled = state === "done";
  }

  function play() {
    window.clearTimeout(timer);
    reset();
    controls.hidden = false;
    queue = buildQueue();
    index = 0;
    state = "playing";
    render();
    schedule(queue[0][0]);
  }

  // The finished replay leaves the same screen as the static page, plus the
  // row it moved to.
  function finish() {
    window.clearTimeout(timer);
    state = "done";
    screen.dataset.view = "tui";
    command.textContent = typed;
    rows.forEach((row) => {
      row.hidden = false;
    });
    count.textContent = String(rows.length);
    details.hidden = true;
    keycap.hidden = true;
    if (document.activeElement === toggle) replay.focus();
    render();
  }

  toggle.addEventListener("click", () => {
    if (state === "playing") {
      window.clearTimeout(timer);
      remaining = Math.max(0, due - performance.now());
      state = "paused";
    } else if (state === "paused") {
      state = "playing";
      schedule(remaining);
    }
    render();
  });
  replay.addEventListener("click", play);

  const observer = new IntersectionObserver(
    (entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      observer.disconnect();
      if (!reduced.matches) play();
    },
    { threshold: 0.35 },
  );
  if (!reduced.matches) {
    // Show the empty shell before the replay starts so the records don't flash.
    reset();
    observer.observe(demo);
  }
  reduced.addEventListener("change", () => {
    if (!reduced.matches) return;
    observer.disconnect();
    finish();
    controls.hidden = true;
  });
}

setUpCopyButtons();
setUpDemo();
loadRelease();
