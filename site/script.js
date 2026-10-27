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

// The recorded header leaves room for "vX.Y.Z"; the latest release fills it in.
let releaseTag = "";

function fillVersion(root) {
  for (const version of root.querySelectorAll("[data-version]")) {
    version.textContent = releaseTag.padEnd(version.textContent.length);
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
    releaseTag = release.tag_name;
    fillVersion(document);
  } catch {
    // Offline or rate limited: keep the link to the Releases page.
  }
}

// Each scene replays frames that scripts.demos recorded from the real app.
// reset() shows the shell, steps(at) queues [delay, action] pairs, and finish()
// restores the last frame, which is also the static screen without JavaScript.
function frameScene(demo, frames) {
  const screen = demo.querySelector(".screen");
  const command = demo.querySelector("[data-shell-command]");
  const typed = command.textContent;
  const tui = demo.querySelector("[data-frame]");
  const keycap = demo.querySelector("[data-keycap]");
  const show = (frame) => {
    tui.innerHTML = frame;
    fillVersion(tui);
  };
  const press = (key) => {
    keycap.textContent = key;
    keycap.hidden = false;
  };
  return {
    reset() {
      screen.dataset.view = "shell";
      command.textContent = "";
      keycap.hidden = true;
    },
    steps(at) {
      for (const character of typed) {
        at(character === " " ? 70 : 35, () => command.append(character));
      }
      at(450, () => press("⏎"));
      at(400, () => {
        keycap.hidden = true;
        show(frames[0].html);
        screen.dataset.view = "tui";
      });
      frames.slice(1).forEach((frame, index) => {
        at(frames[index].delay, () => press(frame.key ?? ""));
        at(150, () => show(frame.html));
      });
      at(frames.at(-1).delay, () => {
        keycap.hidden = true;
      });
    },
    finish() {
      screen.dataset.view = "tui";
      command.textContent = typed;
      keycap.hidden = true;
      show(frames.at(-1).html);
    },
  };
}

async function loadScenes(section) {
  const response = await fetch("demos.json");
  if (!response.ok) throw new Error(`demos.json returned ${response.status}`);
  const { lines, demos } = await response.json();
  return Object.fromEntries(
    Object.entries(demos).map(([name, { frames }]) => [
      name,
      frameScene(
        section.querySelector(`[data-demo="${name}"]`),
        frames.map((frame) => ({ ...frame, html: frame.lines.map((i) => lines[i]).join("\n") })),
      ),
    ]),
  );
}

// One player drives the selected mode's scene; the tabs pick the mode.
async function setUpDemos() {
  const section = document.querySelector("#demo");
  const tabs = [...section.querySelectorAll("[data-demo-tab]")];
  const controls = section.querySelector(".demo-controls");
  if (!tabs.length || !controls || !("IntersectionObserver" in window)) return;
  const toggle = controls.querySelector("[data-demo-toggle]");
  const replay = controls.querySelector("[data-demo-replay]");
  const progress = controls.querySelector("[data-demo-progress]");
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  let scenes;
  try {
    scenes = await loadScenes(section);
  } catch {
    // Without the recording, every mode keeps its static last frame.
    return;
  }

  let scene = null;
  let queue = [];
  let index = 0;
  let timer = 0;
  let due = 0;
  let remaining = 0;
  let state = "idle";
  let seen = false;
  let total = 0;
  let played = 0;

  // Milliseconds of the replay shown so far, for the progress bar.
  function position() {
    if (state === "done") return total;
    if (state === "paused") return played + queue[index][0] - remaining;
    if (state === "playing") return played + queue[index][0] - Math.max(0, due - performance.now());
    return 0;
  }

  function drawProgress() {
    const percent = total ? Math.min(100, (100 * position()) / total) : 0;
    progress.firstElementChild.style.width = `${percent}%`;
    progress.setAttribute("aria-valuenow", String(Math.round(percent)));
    progress.dataset.state = state;
    if (state === "playing") window.requestAnimationFrame(drawProgress);
  }

  function tick() {
    const [delay, action] = queue[index];
    played += delay;
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
    played = 0;
    total = queue.reduce((sum, [delay]) => sum + delay, 0);
    state = "playing";
    render();
    schedule(queue[0][0]);
    drawProgress();
  }

  function finish() {
    window.clearTimeout(timer);
    state = "done";
    scene.finish();
    if (document.activeElement === toggle) replay.focus();
    render();
    drawProgress();
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
    if (seen) {
      play();
      return;
    }
    // Waiting for the first scroll into view: the replay hasn't started.
    scene.reset();
    state = "idle";
    render();
    drawProgress();
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
    drawProgress();
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
