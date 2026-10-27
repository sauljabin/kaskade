"use strict";

// Progressive enhancement only: without this script the page shows each mode's
// final screen and the install commands as plain text.

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

// Each scene replays one mode over its static final screen. reset() shows the
// starting state, steps(at) queues [delay, action] pairs, and finish() restores
// the static screen, so stopping at any point leaves a complete picture.
function sceneBase(demo) {
  const screen = demo.querySelector(".screen");
  const command = demo.querySelector("[data-shell-command]");
  const typed = command.textContent;
  const keycap = demo.querySelector("[data-keycap]");
  const press = (key) => {
    keycap.textContent = key;
    keycap.hidden = false;
  };
  return {
    press,
    reset() {
      screen.dataset.view = "shell";
      command.textContent = "";
      keycap.hidden = true;
    },
    start(at) {
      for (const character of typed) {
        at(character === " " ? 70 : 35, () => command.append(character));
      }
      at(450, () => press("⏎"));
      at(400, () => {
        keycap.hidden = true;
        screen.dataset.view = "tui";
      });
    },
    finish() {
      screen.dataset.view = "tui";
      command.textContent = typed;
      keycap.hidden = true;
    },
  };
}

function selectRow(rows, position) {
  rows.forEach((row, index) => row.classList.toggle("selected", index === position));
}

// Topic metadata renders first; record and group metrics fill in afterwards.
function adminScene(demo) {
  const base = sceneBase(demo);
  const rows = [...demo.querySelectorAll("[data-records] tr")];
  const metrics = [...demo.querySelectorAll("[data-metric]")];
  const values = metrics.map((cell) => cell.textContent);
  const details = demo.querySelector("[data-details]");
  const showMetrics = (row) =>
    row.querySelectorAll("[data-metric]").forEach((cell) => {
      cell.textContent = values[metrics.indexOf(cell)];
    });
  return {
    reset() {
      base.reset();
      metrics.forEach((cell) => {
        cell.textContent = "…";
      });
      selectRow(rows, 0);
      details.hidden = true;
    },
    steps(at) {
      base.start(at);
      rows.forEach((row) => at(rows.indexOf(row) ? 120 : 1100, () => showMetrics(row)));
      at(1200, () => base.press("j"));
      at(150, () => selectRow(rows, 1));
      at(550, () => base.press("j"));
      at(150, () => selectRow(rows, 2));
      at(800, () => base.press("d"));
      at(150, () => {
        details.hidden = false;
      });
      at(3600, () => base.press("esc"));
      at(150, () => {
        details.hidden = true;
      });
    },
    finish() {
      base.finish();
      rows.forEach(showMetrics);
      details.hidden = true;
    },
  };
}

function consumerScene(demo) {
  const base = sceneBase(demo);
  const count = demo.querySelector("[data-count]");
  const rows = [...demo.querySelectorAll("[data-records] tr")];
  const details = demo.querySelector("[data-details]");

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

  return {
    reset() {
      base.reset();
      rows.forEach((row) => {
        row.hidden = true;
      });
      count.textContent = "0";
      selectRow(rows, 0);
      details.hidden = true;
    },
    steps(at) {
      base.start(at);
      rows.forEach((row, index) => {
        at(index ? 140 : 700, () => {
          row.hidden = false;
          count.textContent = String(index + 1);
        });
      });
      at(1200, () => base.press("j"));
      at(150, () => selectRow(rows, 1));
      at(550, () => base.press("j"));
      at(150, () => selectRow(rows, 2));
      at(800, () => base.press("⏎"));
      at(150, () => showDetails(rows[2]));
      at(3600, () => base.press("esc"));
      at(150, () => {
        details.hidden = true;
      });
    },
    finish() {
      base.finish();
      rows.forEach((row) => {
        row.hidden = false;
      });
      count.textContent = String(rows.length);
      details.hidden = true;
    },
  };
}

function producerScene(demo) {
  const base = sceneBase(demo);
  const toast = demo.querySelector("[data-toast]");
  return {
    reset() {
      base.reset();
      toast.hidden = true;
    },
    steps(at) {
      base.start(at);
      at(2400, () => base.press("^s"));
      at(450, () => {
        toast.hidden = false;
      });
      at(3600, () => {
        toast.hidden = true;
      });
    },
    finish() {
      base.finish();
      toast.hidden = true;
    },
  };
}

const SCENES = { admin: adminScene, consumer: consumerScene, producer: producerScene };

// One player drives the selected mode's scene; the tabs pick the mode.
function setUpDemos() {
  const section = document.querySelector("#demo");
  const tabs = [...section.querySelectorAll("[data-demo-tab]")];
  const controls = section.querySelector(".demo-controls");
  if (!tabs.length || !controls || !("IntersectionObserver" in window)) return;
  const toggle = controls.querySelector("[data-demo-toggle]");
  const replay = controls.querySelector("[data-demo-replay]");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  const scenes = Object.fromEntries(
    tabs.map((tab) => {
      const name = tab.dataset.demoTab;
      return [name, SCENES[name](section.querySelector(`[data-demo="${name}"]`))];
    }),
  );

  let scene = null;
  let queue = [];
  let index = 0;
  let timer = 0;
  let due = 0;
  let remaining = 0;
  let state = "idle";
  let seen = false;

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
    scene.reset();
    queue = [];
    scene.steps((delay, action) => queue.push([delay, action]));
    queue.push([900, finish]);
    index = 0;
    state = "playing";
    render();
    schedule(queue[0][0]);
  }

  function finish() {
    window.clearTimeout(timer);
    state = "done";
    scene.finish();
    if (document.activeElement === toggle) replay.focus();
    render();
  }

  function select(tab) {
    if (scene) finish();
    for (const other of tabs) {
      const selected = other === tab;
      other.setAttribute("aria-selected", String(selected));
      other.tabIndex = selected ? 0 : -1;
      document.getElementById(other.getAttribute("aria-controls")).hidden = !selected;
    }
    scene = scenes[tab.dataset.demoTab];
    if (reduced.matches) return;
    if (seen) play();
    else scene.reset();
  }

  section.querySelector("[role=tablist]").hidden = false;
  for (const tab of tabs) {
    document.getElementById(tab.getAttribute("aria-controls")).setAttribute("role", "tabpanel");
    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", (event) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      const next = tabs[(tabs.indexOf(tab) + step + tabs.length) % tabs.length];
      next.focus();
      select(next);
    });
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
  select(tabs[0]);
  controls.hidden = reduced.matches;

  const observer = new IntersectionObserver(
    (entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return;
      observer.disconnect();
      seen = true;
      if (!reduced.matches) play();
    },
    { threshold: 0.25 },
  );
  if (!reduced.matches) observer.observe(section);
  reduced.addEventListener("change", () => {
    if (!reduced.matches) return;
    observer.disconnect();
    finish();
    controls.hidden = true;
  });
}

setUpCopyButtons();
setUpDemos();
loadRelease();
