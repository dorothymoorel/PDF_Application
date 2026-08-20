// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FocusTrapDialog } from "./focus-trap-dialog";

afterEach(() => {
  cleanup();
});

describe("editor accessibility primitives", () => {
  it("traps Tab focus, closes with Escape, and restores focus", () => {
    const previouslyFocused = document.createElement("button");
    document.body.append(previouslyFocused);
    previouslyFocused.focus();
    const onClose = vi.fn();

    const { unmount } = render(
      <FocusTrapDialog onClose={onClose} title="Review conflict">
        <button type="button">Confirm</button>
      </FocusTrapDialog>,
    );

    const closeButton = screen.getByRole("button", { name: "Close dialog" });
    const confirmButton = screen.getByRole("button", { name: "Confirm" });
    expect(screen.getByRole("dialog", { name: "Review conflict" }).getAttribute("aria-modal")).toBe(
      "true",
    );
    expect(document.activeElement).toBe(closeButton);

    fireEvent.keyDown(closeButton, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(confirmButton);
    fireEvent.keyDown(confirmButton, { key: "Tab" });
    expect(document.activeElement).toBe(closeButton);
    fireEvent.keyDown(closeButton, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();

    unmount();
    expect(document.activeElement).toBe(previouslyFocused);
    previouslyFocused.remove();
  });
});
