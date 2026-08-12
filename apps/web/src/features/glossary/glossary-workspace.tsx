"use client";

import { useEffect, useState } from "react";

import {
  GLOSSARY_RULE_TYPES,
  GLOSSARY_SCOPES,
  type GlossaryCandidate,
  type GlossaryConflict,
  type GlossaryOccurrence,
  type GlossaryRuleType,
  type GlossaryScope,
  type GlossaryTerm,
  type GlossaryUiClient,
  type SaveGlossaryTermInput,
} from "./types";

const TARGET_REQUIRED_RULES = new Set<GlossaryRuleType>([
  "TRANSLATE_AS",
  "ORIGINAL_THEN_TRANSLATION",
  "TRANSLATION_THEN_ORIGINAL",
]);

interface TermFormState {
  sourceTerm: string;
  targetTerm: string;
  ruleType: GlossaryRuleType;
  scope: GlossaryScope;
  priority: string;
  caseSensitive: boolean;
  wholeWord: boolean;
}

const EMPTY_FORM: TermFormState = {
  sourceTerm: "",
  targetTerm: "",
  ruleType: "KEEP_ORIGINAL",
  scope: "PROJECT",
  priority: "100",
  caseSensitive: false,
  wholeWord: true,
};

function humanize(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((word) => `${word.charAt(0).toUpperCase()}${word.slice(1)}`)
    .join(" ");
}

function toFormState(term: GlossaryTerm): TermFormState {
  return {
    sourceTerm: term.sourceTerm,
    targetTerm: term.targetTerm ?? "",
    ruleType: term.ruleType,
    scope: term.scope,
    priority: String(term.priority),
    caseSensitive: term.caseSensitive,
    wholeWord: term.wholeWord,
  };
}

function validateForm(form: TermFormState): Record<string, string> {
  const errors: Record<string, string> = {};
  if (form.sourceTerm.trim() === "") {
    errors.sourceTerm = "Source term is required.";
  }
  if (TARGET_REQUIRED_RULES.has(form.ruleType) && form.targetTerm.trim() === "") {
    errors.targetTerm = "Target term is required for this rule.";
  }
  const priority = Number(form.priority);
  if (!Number.isInteger(priority) || priority < 0) {
    errors.priority = "Priority must be a non-negative whole number.";
  }
  return errors;
}

function toSaveInput(form: TermFormState): SaveGlossaryTermInput {
  const trimmedTarget = form.targetTerm.trim();
  return {
    sourceTerm: form.sourceTerm.trim(),
    targetTerm: TARGET_REQUIRED_RULES.has(form.ruleType) ? trimmedTarget : null,
    ruleType: form.ruleType,
    scope: form.scope,
    priority: Number(form.priority),
    caseSensitive: form.caseSensitive,
    wholeWord: form.wholeWord,
  };
}

const inputClass =
  "mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950";
const buttonClass =
  "rounded-lg bg-blue-700 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-800 disabled:cursor-not-allowed disabled:opacity-50";

export function GlossaryWorkspace({
  client,
  glossaryId,
  projectId,
}: Readonly<{
  client: GlossaryUiClient;
  glossaryId: string;
  projectId: string;
}>) {
  const [terms, setTerms] = useState<readonly GlossaryTerm[]>([]);
  const [candidates, setCandidates] = useState<readonly GlossaryCandidate[]>([]);
  const [conflicts, setConflicts] = useState<readonly GlossaryConflict[]>([]);
  const [occurrences, setOccurrences] = useState<readonly GlossaryOccurrence[]>([]);
  const [occurrenceTerm, setOccurrenceTerm] = useState<GlossaryTerm | null>(null);
  const [form, setForm] = useState<TermFormState>(EMPTY_FORM);
  const [editingTerm, setEditingTerm] = useState<GlossaryTerm | null>(null);
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    setError(null);

    void Promise.all([
      client.listTerms(glossaryId),
      client.listCandidates(projectId),
      client.listConflicts(projectId),
    ])
      .then(([nextTerms, nextCandidates, nextConflicts]) => {
        if (active) {
          setTerms(nextTerms);
          setCandidates(nextCandidates);
          setConflicts(nextConflicts);
        }
      })
      .catch(() => {
        if (active) {
          setError("Glossary data could not be loaded.");
        }
      })
      .finally(() => {
        if (active) {
          setIsLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [client, glossaryId, projectId]);

  const updateForm = <Key extends keyof TermFormState>(key: Key, value: TermFormState[Key]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setFormErrors((current) => {
      if (!(key in current)) {
        return current;
      }
      const next = { ...current };
      delete next[key];
      return next;
    });
  };

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setEditingTerm(null);
    setFormErrors({});
  };

  const saveTerm = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const errors = validateForm(form);
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }

    setPendingAction("save-term");
    setError(null);
    try {
      const input = toSaveInput(form);
      if (editingTerm === null) {
        const created = await client.createTerm(glossaryId, input);
        setTerms((current) => [...current, created]);
      } else {
        const updated = await client.updateTerm(editingTerm.id, {
          ...input,
          expectedRevision: editingTerm.currentRevision,
        });
        setTerms((current) =>
          current.map((term) => (term.id === updated.id ? updated : term)),
        );
      }
      resetForm();
    } catch {
      setError("The glossary term could not be saved.");
    } finally {
      setPendingAction(null);
    }
  };

  const editTerm = (term: GlossaryTerm) => {
    setEditingTerm(term);
    setForm(toFormState(term));
    setFormErrors({});
  };

  const viewOccurrences = async (term: GlossaryTerm) => {
    setOccurrenceTerm(term);
    setOccurrences([]);
    setPendingAction(`occurrences:${term.id}`);
    setError(null);
    try {
      setOccurrences(await client.listOccurrences(term.id));
    } catch {
      setError("Occurrences could not be loaded.");
    } finally {
      setPendingAction(null);
    }
  };

  const deactivateTerm = async (term: GlossaryTerm) => {
    setPendingAction(`deactivate:${term.id}`);
    setError(null);
    try {
      await client.deactivateTerm(term.id);
      setTerms((current) => current.filter((item) => item.id !== term.id));
      if (occurrenceTerm?.id === term.id) {
        setOccurrenceTerm(null);
        setOccurrences([]);
      }
      if (editingTerm?.id === term.id) {
        resetForm();
      }
    } catch {
      setError("The glossary term could not be deactivated.");
    } finally {
      setPendingAction(null);
    }
  };

  const acceptCandidate = async (candidate: GlossaryCandidate) => {
    setPendingAction(`candidate:${candidate.id}`);
    setError(null);
    try {
      await client.acceptCandidate(candidate.id, {
        glossaryId,
        ruleType: "KEEP_ORIGINAL",
        targetTerm: null,
        scope: "PROJECT",
      });
      setCandidates((current) => current.filter((item) => item.id !== candidate.id));
    } catch {
      setError("The candidate could not be accepted.");
    } finally {
      setPendingAction(null);
    }
  };

  const rejectCandidate = async (candidate: GlossaryCandidate) => {
    setPendingAction(`candidate:${candidate.id}`);
    setError(null);
    try {
      await client.rejectCandidate(candidate.id, "Rejected during glossary review.");
      setCandidates((current) => current.filter((item) => item.id !== candidate.id));
    } catch {
      setError("The candidate could not be rejected.");
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <main className="space-y-6" aria-busy={isLoading}>
      <header>
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-700">Terminology</p>
        <h1 className="text-2xl font-bold text-slate-950">Glossary workspace</h1>
        <p className="mt-1 text-sm text-slate-600">
          Maintain translation rules and review detected terminology before translation.
        </p>
      </header>

      {isLoading ? <p role="status">Loading glossary...</p> : null}
      {error === null ? null : (
        <p className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800" role="alert">
          {error}
        </p>
      )}

      <section aria-labelledby="term-form-heading" className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-slate-950" id="term-form-heading">
          {editingTerm === null ? "Add term" : `Edit ${editingTerm.sourceTerm}`}
        </h2>
        <form
          className="mt-4 grid gap-4 md:grid-cols-2"
          noValidate
          onSubmit={(event) => void saveTerm(event)}
        >
          <label className="text-sm font-medium text-slate-800">
            Source term
            <input
              aria-describedby={formErrors.sourceTerm === undefined ? undefined : "source-term-error"}
              aria-invalid={formErrors.sourceTerm !== undefined}
              className={inputClass}
              onChange={(event) => updateForm("sourceTerm", event.target.value)}
              value={form.sourceTerm}
            />
            {formErrors.sourceTerm === undefined ? null : (
              <span className="mt-1 block text-red-700" id="source-term-error">
                {formErrors.sourceTerm}
              </span>
            )}
          </label>

          <label className="text-sm font-medium text-slate-800">
            Rule type
            <select
              className={inputClass}
              onChange={(event) => updateForm("ruleType", event.target.value as GlossaryRuleType)}
              value={form.ruleType}
            >
              {GLOSSARY_RULE_TYPES.map((rule) => (
                <option key={rule} value={rule}>
                  {humanize(rule)}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm font-medium text-slate-800">
            Target term
            <input
              aria-describedby={formErrors.targetTerm === undefined ? undefined : "target-term-error"}
              aria-invalid={formErrors.targetTerm !== undefined}
              className={inputClass}
              disabled={!TARGET_REQUIRED_RULES.has(form.ruleType)}
              onChange={(event) => updateForm("targetTerm", event.target.value)}
              value={form.targetTerm}
            />
            {formErrors.targetTerm === undefined ? null : (
              <span className="mt-1 block text-red-700" id="target-term-error">
                {formErrors.targetTerm}
              </span>
            )}
          </label>

          <label className="text-sm font-medium text-slate-800">
            Scope
            <select
              className={inputClass}
              onChange={(event) => updateForm("scope", event.target.value as GlossaryScope)}
              value={form.scope}
            >
              {GLOSSARY_SCOPES.map((scope) => (
                <option key={scope} value={scope}>
                  {humanize(scope)}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm font-medium text-slate-800">
            Priority
            <input
              aria-describedby={formErrors.priority === undefined ? undefined : "priority-error"}
              aria-invalid={formErrors.priority !== undefined}
              className={inputClass}
              min="0"
              onChange={(event) => updateForm("priority", event.target.value)}
              step="1"
              type="number"
              value={form.priority}
            />
            {formErrors.priority === undefined ? null : (
              <span className="mt-1 block text-red-700" id="priority-error">
                {formErrors.priority}
              </span>
            )}
          </label>

          <fieldset className="flex flex-wrap items-center gap-5 text-sm text-slate-800">
            <legend className="sr-only">Matching options</legend>
            <label className="flex items-center gap-2">
              <input
                checked={form.caseSensitive}
                onChange={(event) => updateForm("caseSensitive", event.target.checked)}
                type="checkbox"
              />
              Case sensitive
            </label>
            <label className="flex items-center gap-2">
              <input
                checked={form.wholeWord}
                onChange={(event) => updateForm("wholeWord", event.target.checked)}
                type="checkbox"
              />
              Whole word
            </label>
          </fieldset>

          <div className="flex gap-2 md:col-span-2">
            <button className={buttonClass} disabled={pendingAction === "save-term"} type="submit">
              {editingTerm === null ? "Add term" : "Save changes"}
            </button>
            {editingTerm === null ? null : (
              <button
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-800"
                onClick={resetForm}
                type="button"
              >
                Cancel
              </button>
            )}
          </div>
        </form>
      </section>

      <section aria-labelledby="terms-heading" className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-slate-950" id="terms-heading">
          Terms
        </h2>
        {terms.length === 0 && !isLoading ? (
          <p className="mt-3 text-sm text-slate-600">No glossary terms yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-200">
            {terms.map((term) => (
              <li className="flex flex-wrap items-center justify-between gap-3 py-3" key={term.id}>
                <div>
                  <p className="font-semibold text-slate-950">{term.sourceTerm}</p>
                  <p className="text-sm text-slate-600">
                    {humanize(term.ruleType)} · {term.targetTerm ?? "Preserve source"} · {humanize(term.scope)}
                  </p>
                  <p className="text-xs text-slate-500">{term.occurrenceCount} occurrences</p>
                </div>
                <div className="flex gap-2">
                  <button
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold"
                    onClick={() => editTerm(term)}
                    type="button"
                  >
                    Edit {term.sourceTerm}
                  </button>
                  <button
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold"
                    disabled={pendingAction === `occurrences:${term.id}`}
                    onClick={() => void viewOccurrences(term)}
                    type="button"
                  >
                    View occurrences for {term.sourceTerm}
                  </button>
                  <button
                    className="rounded-lg border border-red-300 px-3 py-2 text-sm font-semibold text-red-800"
                    disabled={pendingAction === `deactivate:${term.id}`}
                    onClick={() => void deactivateTerm(term)}
                    type="button"
                  >
                    Deactivate {term.sourceTerm}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="candidates-heading" className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-slate-950" id="candidates-heading">
          Candidate queue
        </h2>
        {candidates.length === 0 && !isLoading ? (
          <p className="mt-3 text-sm text-slate-600">No candidates awaiting review.</p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-200">
            {candidates.map((candidate) => (
              <li className="flex flex-wrap items-center justify-between gap-3 py-3" key={candidate.id}>
                <div>
                  <p className="font-semibold text-slate-950">{candidate.sourceTerm}</p>
                  <p className="text-sm text-slate-600">
                    {humanize(candidate.candidateType)} · {candidate.occurrenceCount} occurrences ·{" "}
                    {Math.round(candidate.confidence * 100)}% confidence
                  </p>
                </div>
                <div className="flex gap-2">
                  <button
                    className={buttonClass}
                    disabled={pendingAction === `candidate:${candidate.id}`}
                    onClick={() => void acceptCandidate(candidate)}
                    type="button"
                  >
                    Accept {candidate.sourceTerm} as Keep Original
                  </button>
                  <button
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold"
                    disabled={pendingAction === `candidate:${candidate.id}`}
                    onClick={() => void rejectCandidate(candidate)}
                    type="button"
                  >
                    Reject {candidate.sourceTerm}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="conflicts-heading" className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-slate-950" id="conflicts-heading">
          Conflicts
        </h2>
        {conflicts.length === 0 && !isLoading ? (
          <p className="mt-3 text-sm text-slate-600">No glossary conflicts detected.</p>
        ) : (
          <ul className="mt-3 space-y-3">
            {conflicts.map((conflict) => (
              <li className="rounded-xl border border-amber-300 bg-amber-50 p-3" key={conflict.id}>
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-semibold text-slate-950">{conflict.sourceTerm}</p>
                  <span className="rounded-full bg-slate-900 px-2 py-0.5 text-xs font-semibold text-white">
                    {conflict.blocking ? "Blocking" : "Warning"}
                  </span>
                  <span className="text-xs font-medium text-slate-700">
                    {humanize(conflict.conflictType)}
                  </span>
                </div>
                <p className="mt-1 text-sm text-slate-700">{conflict.explanation}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="occurrences-heading" className="rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-slate-950" id="occurrences-heading">
          Occurrences
        </h2>
        {occurrenceTerm === null ? (
          <p className="mt-3 text-sm text-slate-600">Select a term to inspect its occurrences.</p>
        ) : occurrences.length === 0 && pendingAction !== `occurrences:${occurrenceTerm.id}` ? (
          <p className="mt-3 text-sm text-slate-600">
            No occurrences found for {occurrenceTerm.sourceTerm}.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-slate-200">
            {occurrences.map((occurrence) => (
              <li className="py-3" key={occurrence.id}>
                <p className="font-semibold text-slate-950">{occurrence.matchedText}</p>
                <p className="text-sm text-slate-700">{occurrence.sourceContext}</p>
                <p className="text-sm text-slate-600">
                  Translation: {occurrence.finalTranslation ?? "Not translated"} · Page {occurrence.pageId}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
