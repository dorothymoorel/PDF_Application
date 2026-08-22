// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExportPanel } from "./export-panel";
import type { ExportClient } from "./types";

afterEach(() => cleanup());

describe("export panel", () => {
  it("creates an export and downloads the completed PDF", async () => {
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const createObjectUrl = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:export");
    const client: ExportClient = {
      createExport: vi.fn().mockResolvedValue({
        id: "exp_1",
        filename: "translated.pdf",
        status: "COMPLETED",
      }),
      downloadExport: vi.fn().mockResolvedValue(new Blob(["pdf"], { type: "application/pdf" })),
    };
    render(<ExportPanel client={client} projectId="prj_1" />);

    fireEvent.click(screen.getByRole("button", { name: "Create export" }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(client.createExport).toHaveBeenCalledWith({ profile: "STANDARD", projectId: "prj_1" });
    expect(screen.getByText("translated.pdf · Completed")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Download PDF" }));
    await act(async () => {
      await Promise.resolve();
    });
    expect(client.downloadExport).toHaveBeenCalledWith("exp_1");
    expect(createObjectUrl).toHaveBeenCalled();
    expect(anchorClick).toHaveBeenCalled();
    anchorClick.mockRestore();
    createObjectUrl.mockRestore();
  });
});
