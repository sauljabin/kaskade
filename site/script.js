const statusRegion = document.querySelector(".copy-status");
let resetTimer;

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
