import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import RootLayout, { metadata } from "../app/layout";
import Home from "../app/page";

describe("application shell", () => {
  it("renders the TransLoka root page", () => {
    const page = renderToStaticMarkup(createElement(Home));

    expect(page).toContain("TransLoka");
    expect(page).toContain("Local-First Personal PDF Translation Application");
  });

  it("provides a valid root layout", () => {
    const layout = renderToStaticMarkup(
      RootLayout({ children: createElement("main", null, "Test content") }),
    );

    expect(layout).toContain('<html lang="en">');
    expect(layout).toContain("<body>");
    expect(layout).toContain("Test content");
    expect(metadata.title).toBe("TransLoka");
  });
});
