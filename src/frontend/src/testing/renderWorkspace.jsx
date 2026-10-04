import { render as renderReact } from "@testing-library/react";
import { vi } from "vitest";

import { WorkspaceProvider } from "../../packages/workspace-ui/src/runtime/WorkspaceProvider";

export function render(ui, options) {
  const host = {
    api: { resourceUrl: (path) => path, dispose: vi.fn() },
    storage: window.localStorage,
  };
  return renderReact(ui, {
    ...options,
    wrapper: ({ children }) => <WorkspaceProvider host={host}>{children}</WorkspaceProvider>,
  });
}
