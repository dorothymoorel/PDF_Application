export type UnsavedChangeState = Readonly<{
  currentValue: string;
  savedValue: string;
}>;

export function createUnsavedChangeState(value: string): UnsavedChangeState {
  return { currentValue: value, savedValue: value };
}

export function updateDraft(state: UnsavedChangeState, value: string): UnsavedChangeState {
  return { currentValue: value, savedValue: state.savedValue };
}

export function commitDraft(
  state: UnsavedChangeState,
  savedValue = state.currentValue,
): UnsavedChangeState {
  return { currentValue: savedValue, savedValue };
}

export function hasUnsavedChanges(state: UnsavedChangeState): boolean {
  return state.currentValue !== state.savedValue;
}
