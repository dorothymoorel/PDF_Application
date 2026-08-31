// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExportPanel } from "./export-panel";
import type { ExportClient } from "./types";

afterEach(() => cleanup());

describe("export panel", () => {
  it("loads a validated export, shows its checksum, and downloads the PDF", async () => {
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:export");
    const client: ExportClient = {
      listExports: vi.fn().mockResolvedValue([{
        id: "exp_00000000-0000-4000-8000-000000000001",
        output_profile: "STANDARD",
        version_number: 1,
        filename: "translated.pdf",
        status: "COMPLETED",
        checksum_sha256: "a".repeat(64),
      }]),
      downloadExport: vi.fn().mockResolvedValue(new Blob(["pdf"], { type: "application/pdf" })),
    };
    render(<ExportPanel client={client} projectId="prj_1" />);

    expect(await screen.findByText(/translated.pdf · Completed · version 1/)).toBeTruthy();
    expect(client.listExports).toHaveBeenCalledWith("prj_1");
    expect(screen.getByText(`SHA-256: ${"a".repeat(64)}`)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(client.downloadExport).toHaveBeenCalledWith(
      "exp_00000000-0000-4000-8000-000000000001",
    );
    expect(createObjectUrl).toHaveBeenCalled();
    expect(anchorClick).toHaveBeenCalled();
    anchorClick.mockRestore();
    createObjectUrl.mockRestore();
  });
});
