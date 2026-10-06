/* Make the composer command buttons one press.
 *
 * Chainlit command buttons only stage the command in the composer; the user
 * still has to press the send arrow to run it. Ingest, Delete, and Demo are
 * all single-purpose modes with nothing to type, so submit the command as
 * soon as its button is clicked.
 *
 * Chainlit renders a button command as a `<button class="command-button">`
 * and the send button as `#chat-submit`. A plain command (the popover in
 * `#command-button`) is not matched, so it keeps the usual select-then-send.
 */
document.addEventListener("click", (event) => {
  if (!event.target.closest(".command-button")) {
    return;
  }
  // React applies the selected-command state before this macrotask runs, so
  // the send button is enabled by the time we click it. A second click on an
  // already-selected command deselects it, leaving the send button disabled,
  // so this is a no-op.
  setTimeout(() => {
    const send = document.getElementById("chat-submit");
    if (send && !send.disabled) {
      send.click();
    }
  }, 0);
});
