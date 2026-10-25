import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { ApiError, isUnauthenticated } from "../api/client";
import { currentUserKey } from "../features/auth/api";
import { router } from "../routes/router";
import { ThemeSelectionProvider } from "./ThemeSelection";

// An expired/revoked session anywhere sends the user back to sign-in.
const onError = (error: unknown) => {
  if (isUnauthenticated(error)) queryClient.setQueryData(currentUserKey, null);
};

const queryClient = new QueryClient({
  queryCache: new QueryCache({ onError }),
  mutationCache: new MutationCache({ onError }),
  defaultOptions: {
    queries: {
      retry: (failureCount, error) =>
        !(error instanceof ApiError && error.status < 500) && failureCount < 2,
      refetchOnWindowFocus: true,
    },
  },
});

export function App() {
  return (
    <ThemeSelectionProvider>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ThemeSelectionProvider>
  );
}
