import { useCallback, useEffect, useState } from "react";

import {
  commitDraft,
  createUnsavedChangeState,
  hasUnsavedChanges,
  updateDraft,
  type UnsavedChangeState,
} from "../state/unsaved-change-state";

export type NavigationKind = "page" | "segment";

type ConfirmNavigation = (message: string) => boolean;

export type UseUnsavedChangesOptions = Readonly<{
  confirmNavigation?: ConfirmNavigation;
  initialValue: string;
}>;

export type UnsavedChangesController = Readonly<{
  canNavigate(kind: NavigationKind): boolean;
  draft: string;
  isDirty: boolean;
  markSaved(value?: string): void;
  requestPageNavigation(): boolean;
  requestSegmentNavigation(): boolean;
  savedValue: string;
  setDraft(value: string): void;
}>;

function confirmInBrowser(message: string): boolean {
  return typeof window === "undefined" ? true : window.confirm(message);
}

function warningFor(kind: NavigationKind): string {
  const destination = kind === "page" ? "page" : "segment";
  return `You have unsaved changes. Leave this ${destination}?`;
}

export function useUnsavedChanges({
  confirmNavigation = confirmInBrowser,
  initialValue,
}: UseUnsavedChangesOptions): UnsavedChangesController {
  const [state, setState] = useState<UnsavedChangeState>(() =>
    createUnsavedChangeState(initialValue),
  );
  const isDirty = hasUnsavedChanges(state);

  const setDraft = useCallback((value: string) => {
    setState((current) => updateDraft(current, value));
  }, []);

  const markSaved = useCallback((value?: string) => {
    setState((current) => commitDraft(current, value ?? current.currentValue));
  }, []);

  const canNavigate = useCallback(
    (kind: NavigationKind) => !isDirty || confirmNavigation(warningFor(kind)),
    [confirmNavigation, isDirty],
  );

  const requestPageNavigation = useCallback(() => canNavigate("page"), [canNavigate]);
  const requestSegmentNavigation = useCallback(() => canNavigate("segment"), [canNavigate]);

  useEffect(() => {
    if (!isDirty || typeof window === "undefined") {
      return;
    }

    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [isDirty]);

  return {
    canNavigate,
    draft: state.currentValue,
    isDirty,
    markSaved,
    requestPageNavigation,
    requestSegmentNavigation,
    savedValue: state.savedValue,
    setDraft,
  };
}
