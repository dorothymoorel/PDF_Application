// @vitest-environment jsdom

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useUnsavedChanges } from "../../apps/web/src/features/editor/hooks/use-unsaved-changes";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("useUnsavedChanges", () => {
  it("allows page and segment navigation when the draft is unchanged", () => {
    const confirmNavigation = vi.fn(() => false);
    const { result } = renderHook(() =>
      useUnsavedChanges({ confirmNavigation, initialValue: "Initial translation" }),
    );

    expect(result.current.isDirty).toBe(false);
    expect(result.current.requestPageNavigation()).toBe(true);
    expect(result.current.requestSegmentNavigation()).toBe(true);
    expect(confirmNavigation).not.toHaveBeenCalled();
  });

  it("warns before dirty page and segment navigation", () => {
    const confirmNavigation = vi.fn(() => false);
    const { result } = renderHook(() =>
      useUnsavedChanges({ confirmNavigation, initialValue: "Initial translation" }),
    );

    act(() => result.current.setDraft("Edited translation"));

    expect(result.current.isDirty).toBe(true);
    expect(result.current.requestPageNavigation()).toBe(false);
    expect(result.current.requestSegmentNavigation()).toBe(false);
    expect(confirmNavigation).toHaveBeenNthCalledWith(
      1,
      "You have unsaved changes. Leave this page?",
    );
    expect(confirmNavigation).toHaveBeenNthCalledWith(
      2,
      "You have unsaved changes. Leave this segment?",
    );
  });

  it("clears the dirty state after a successful save", () => {
    const confirmNavigation = vi.fn(() => false);
    const { result } = renderHook(() =>
      useUnsavedChanges({ confirmNavigation, initialValue: "Initial translation" }),
    );

    act(() => result.current.setDraft("Edited translation"));
    act(() => result.current.markSaved());

    expect(result.current.isDirty).toBe(false);
    expect(result.current.savedValue).toBe("Edited translation");
    expect(result.current.requestSegmentNavigation()).toBe(true);
    expect(confirmNavigation).not.toHaveBeenCalled();
  });

  it("keeps the draft dirty when a save fails", async () => {
    const confirmNavigation = vi.fn(() => false);
    const save = vi.fn(async () => {
      throw new Error("save failed");
    });
    const { result } = renderHook(() =>
      useUnsavedChanges({ confirmNavigation, initialValue: "Initial translation" }),
    );

    act(() => result.current.setDraft("Edited translation"));
    await expect(save()).rejects.toThrow("save failed");

    expect(result.current.isDirty).toBe(true);
    expect(result.current.requestSegmentNavigation()).toBe(false);
    expect(confirmNavigation).toHaveBeenCalledTimes(1);
  });

  it("registers a browser unload warning only while dirty", () => {
    const { result } = renderHook(() =>
      useUnsavedChanges({ initialValue: "Initial translation" }),
    );
    const cleanEvent = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(cleanEvent);
    expect(cleanEvent.defaultPrevented).toBe(false);

    act(() => result.current.setDraft("Edited translation"));
    const dirtyEvent = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirtyEvent);
    expect(dirtyEvent.defaultPrevented).toBe(true);
  });
});
