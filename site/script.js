const statusRegion = document.querySelector(".copy-status");
const releaseRegion = document.querySelector(".hero-release");
const releaseLink = document.querySelector("[data-latest-release]");
const releasesUrl = "https://github.com/sauljabin/kaskade/releases";
let resetTimer;

async function loadLatestRelease() {
  if (!releaseRegion || !releaseLink) {
    return;
  }

  try {
    const response = await fetch(
      "https://api.github.com/repos/sauljabin/kaskade/releases/latest",
      { headers: { Accept: "application/vnd.github+json" } },
    );

    if (!response.ok) {
      throw new Error(`GitHub returned ${response.status}`);
    }

    const release = await response.json();
    if (typeof release.tag_name !== "string" || release.tag_name.length === 0) {
      throw new Error("The latest release did not include a tag");
    }

    releaseLink.textContent = `${release.tag_name} ↗`;
    releaseLink.href = `${releasesUrl}/tag/${encodeURIComponent(release.tag_name)}`;
    releaseRegion.dataset.releaseState = "ready";
  } catch {
    releaseLink.textContent = "View releases ↗";
    releaseLink.href = releasesUrl;
    releaseRegion.dataset.releaseState = "unavailable";
  }
}

async function writeToClipboard(value) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const field = document.createElement("textarea");
  field.value = value;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.append(field);
  field.select();

  const copied = document.execCommand("copy");
  field.remove();

  if (!copied) {
    throw new Error("Copy command was unavailable");
  }
}

function announce(message) {
  window.clearTimeout(resetTimer);
  statusRegion.textContent = "";

  window.requestAnimationFrame(() => {
    statusRegion.textContent = message;
  });

  resetTimer = window.setTimeout(() => {
    statusRegion.textContent = "";
  }, 3000);
}

document.querySelectorAll("[data-copy-target]").forEach((button) => {
  button.addEventListener("click", async () => {
    const command = document.getElementById(button.dataset.copyTarget);

    if (!command) {
      return;
    }

    const originalLabel = button.textContent;

    try {
      await writeToClipboard(command.textContent.trim());
      button.textContent = "Copied";
      button.dataset.copyState = "success";
      announce(`${command.textContent.trim()} copied to clipboard.`);
    } catch {
      announce("Copy unavailable. Select the command and copy it manually.");
    }

    window.setTimeout(() => {
      button.textContent = originalLabel;
      delete button.dataset.copyState;
    }, 2000);
  });
});

loadLatestRelease();
