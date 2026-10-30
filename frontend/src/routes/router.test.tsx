import { render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter, type RouteObject } from "react-router-dom";

import { RouteErrorPage, isChunkLoadError } from "./RouteErrorPage";
import { routes } from "./router";

type Route = RouteObject & { children?: Route[] };

function lazyRoutes(list: Route[]): Route[] {
  return list.flatMap((route) => [...(typeof route.lazy === "function" ? [route] : []), ...lazyRoutes(route.children ?? [])]);
}

describe("route-level code splitting (HIMS-PLAT-015)", () => {
  it("every on-demand screen loads to a real component", async () => {
    const lazy = lazyRoutes(routes as Route[]);
    expect(lazy.length).toBeGreaterThanOrEqual(20);
    for (const route of lazy) {
      const loaded = await (route.lazy as () => Promise<{ Component?: unknown }>)();
      expect(typeof loaded.Component, String(route.path)).toBe("function");
    }
  });

  it("recognises a screen file that disappeared after an update", () => {
    expect(isChunkLoadError(new TypeError("Failed to fetch dynamically imported module: /assets/x.js"))).toBe(true);
    expect(isChunkLoadError(new Error("Importing a module script failed."))).toBe(true);
    expect(isChunkLoadError(new Error("Cannot read properties of undefined"))).toBe(false);
  });

  it("offers a reload when a screen cannot be downloaded", async () => {
    const router = createMemoryRouter(
      [
        {
          path: "/",
          errorElement: <RouteErrorPage />,
          lazy: async () => {
            throw new TypeError("Failed to fetch dynamically imported module: /assets/StaffPage.js");
          },
        },
      ],
      { initialEntries: ["/"] },
    );
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<RouterProvider router={router} />);
    expect(await screen.findByRole("heading", { name: "HIMS was updated" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    vi.restoreAllMocks();
  });

  it("shows a calm message, without technical details, when a screen crashes", async () => {
    function Broken(): never {
      throw new Error("secret internal detail");
    }
    const router = createMemoryRouter([{ path: "/", element: <Broken />, errorElement: <RouteErrorPage /> }]);
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<RouterProvider router={router} />);
    expect(await screen.findByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.queryByText(/secret internal detail/)).not.toBeInTheDocument();
    vi.restoreAllMocks();
  });
});
