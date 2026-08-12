// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GlossaryWorkspace } from "./glossary-workspace";
import type {
  GlossaryCandidate,
  GlossaryConflict,
  GlossaryOccurrence,
  GlossaryTerm,
  GlossaryUiClient,
} from "./types";

const TRANSLATED_TERM: GlossaryTerm = {
  id: "term_1",
  sourceTerm: "pipeline",
  targetTerm: "alur kerja",
  ruleType: "TRANSLATE_AS",
  scope: "PROJECT",
  priority: 100,
  caseSensitive: false,
  wholeWord: true,
  currentRevision: 2,
  occurrenceCount: 3,
};

const CANDIDATES: readonly GlossaryCandidate[] = [
  {
    id: "candidate_1",
    sourceTerm: "workflow",
    occurrenceCount: 4,
    confidence: 0.91,
    candidateType: "REPEATED_TERM",
  },
  {
    id: "candidate_2",
    sourceTerm: "load balancer",
    occurrenceCount: 2,
    confidence: 0.78,
    candidateType: "TECHNICAL_TERM",
  },
];

const BLOCKING_CONFLICT: GlossaryConflict = {
  id: "conflict_1",
  sourceTerm: "pipeline",
  conflictType: "SAME_SCOPE_DIFFERENT_TARGET",
  explanation: "Two active project rules use different target terms.",
  blocking: true,
};

const OCCURRENCE: GlossaryOccurrence = {
  id: "occurrence_1",
  segmentId: "segment_1",
  pageId: "7",
  matchedText: "pipeline",
  sourceContext: "The deployment pipeline completed successfully.",
  finalTranslation: "alur kerja deployment",
};

function fakeClient({
  candidates = [],
  conflicts = [],
  occurrences = [],
  terms = [],
}: Readonly<{
  candidates?: readonly GlossaryCandidate[];
  conflicts?: readonly GlossaryConflict[];
  occurrences?: readonly GlossaryOccurrence[];
  terms?: readonly GlossaryTerm[];
}> = {}): GlossaryUiClient {
  const createdTerm: GlossaryTerm = {
    ...TRANSLATED_TERM,
    id: "term_created",
    sourceTerm: "workflow",
    targetTerm: null,
    ruleType: "KEEP_ORIGINAL",
    currentRevision: 1,
    occurrenceCount: 0,
  };
  const updatedTerm: GlossaryTerm = {
    ...TRANSLATED_TERM,
    targetTerm: "saluran",
    currentRevision: 3,
  };

  return {
    listTerms: vi.fn().mockResolvedValue(terms),
    createTerm: vi.fn().mockResolvedValue(createdTerm),
    updateTerm: vi.fn().mockResolvedValue(updatedTerm),
    deactivateTerm: vi.fn().mockResolvedValue(undefined),
    listCandidates: vi.fn().mockResolvedValue(candidates),
    acceptCandidate: vi.fn().mockResolvedValue(undefined),
    rejectCandidate: vi.fn().mockResolvedValue(undefined),
    listConflicts: vi.fn().mockResolvedValue(conflicts),
    listOccurrences: vi.fn().mockResolvedValue(occurrences),
  };
}

function renderWorkspace(client: GlossaryUiClient) {
  render(<GlossaryWorkspace client={client} glossaryId="glossary_1" projectId="project_1" />);
}

afterEach(cleanup);

describe("glossary workspace", () => {
  it("creates workflow as KEEP_ORIGINAL and edits an existing term", async () => {
    const client = fakeClient({ terms: [TRANSLATED_TERM] });
    renderWorkspace(client);
    await screen.findByText("pipeline");

    fireEvent.change(screen.getByLabelText("Source term"), { target: { value: "workflow" } });
    fireEvent.click(screen.getByRole("button", { name: "Add term" }));

    await waitFor(() =>
      expect(client.createTerm).toHaveBeenCalledWith("glossary_1", {
        sourceTerm: "workflow",
        targetTerm: null,
        ruleType: "KEEP_ORIGINAL",
        scope: "PROJECT",
        priority: 100,
        caseSensitive: false,
        wholeWord: true,
      }),
    );
    expect(await screen.findByText("workflow")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Edit pipeline" }));
    fireEvent.change(screen.getByLabelText("Target term"), { target: { value: "saluran" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(client.updateTerm).toHaveBeenCalledWith("term_1", {
        sourceTerm: "pipeline",
        targetTerm: "saluran",
        ruleType: "TRANSLATE_AS",
        scope: "PROJECT",
        priority: 100,
        caseSensitive: false,
        wholeWord: true,
        expectedRevision: 2,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Deactivate pipeline" }));
    await waitFor(() => expect(client.deactivateTerm).toHaveBeenCalledWith("term_1"));
    expect(screen.queryByRole("button", { name: "Edit pipeline" })).toBeNull();
  });

  it("accepts and rejects detected candidates", async () => {
    const client = fakeClient({ candidates: CANDIDATES });
    renderWorkspace(client);
    await screen.findByText("workflow");

    fireEvent.click(
      screen.getByRole("button", { name: "Accept workflow as Keep Original" }),
    );
    await waitFor(() =>
      expect(client.acceptCandidate).toHaveBeenCalledWith("candidate_1", {
        glossaryId: "glossary_1",
        ruleType: "KEEP_ORIGINAL",
        targetTerm: null,
        scope: "PROJECT",
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Reject load balancer" }));
    await waitFor(() =>
      expect(client.rejectCandidate).toHaveBeenCalledWith(
        "candidate_2",
        "Rejected during glossary review.",
      ),
    );
    expect(await screen.findByText("No candidates awaiting review.")).toBeTruthy();
  });

  it("shows conflict severity and explanation without relying on color", async () => {
    renderWorkspace(fakeClient({ conflicts: [BLOCKING_CONFLICT] }));

    expect(await screen.findByText("Blocking")).toBeTruthy();
    expect(screen.getByText("Same Scope Different Target")).toBeTruthy();
    expect(
      screen.getByText("Two active project rules use different target terms."),
    ).toBeTruthy();
  });

  it("validates required fields before creating a term", async () => {
    const client = fakeClient();
    renderWorkspace(client);
    await screen.findByText("No glossary terms yet.");

    fireEvent.click(screen.getByRole("button", { name: "Add term" }));
    expect(screen.getByText("Source term is required.")).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/^Source term/), { target: { value: "pipeline" } });
    fireEvent.change(screen.getByLabelText("Rule type"), { target: { value: "TRANSLATE_AS" } });
    fireEvent.click(screen.getByRole("button", { name: "Add term" }));

    expect(screen.getByText("Target term is required for this rule.")).toBeTruthy();
    expect(client.createTerm).not.toHaveBeenCalled();
  });

  it("renders empty states and loads occurrences for a selected term", async () => {
    const emptyClient = fakeClient();
    const { unmount } = render(
      <GlossaryWorkspace client={emptyClient} glossaryId="glossary_1" projectId="project_1" />,
    );

    expect(await screen.findByText("No glossary terms yet.")).toBeTruthy();
    expect(screen.getByText("No candidates awaiting review.")).toBeTruthy();
    expect(screen.getByText("No glossary conflicts detected.")).toBeTruthy();
    expect(screen.getByText("Select a term to inspect its occurrences.")).toBeTruthy();
    unmount();

    const populatedClient = fakeClient({ occurrences: [OCCURRENCE], terms: [TRANSLATED_TERM] });
    renderWorkspace(populatedClient);
    await screen.findByText("pipeline");
    fireEvent.click(
      screen.getByRole("button", { name: "View occurrences for pipeline" }),
    );

    expect(
      await screen.findByText("The deployment pipeline completed successfully."),
    ).toBeTruthy();
    expect(screen.getByText("Translation: alur kerja deployment · Page 7")).toBeTruthy();
    expect(populatedClient.listOccurrences).toHaveBeenCalledWith("term_1");
  });
});
