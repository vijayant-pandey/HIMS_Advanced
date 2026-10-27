import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type {
  NumberingPreview,
  NumberingPreviewRequest,
  NumberingScheme,
  NumberingSchemeCreateRequest,
  NumberingSchemeUpdateRequest,
  PaginatedIssuedNumberList,
  SetNextNumberRequest,
} from "../../api/types";

export const numberingKey = ["numbering"] as const;

export function useNumberingSchemes() {
  return useQuery<NumberingScheme[], ApiError>({
    queryKey: [...numberingKey, "schemes"],
    queryFn: ({ signal }) => api.get<NumberingScheme[]>("/numbering-schemes/", { signal }),
  });
}

export function useIssuedNumbers(documentType: string) {
  return useQuery<PaginatedIssuedNumberList, ApiError>({
    queryKey: [...numberingKey, "issued", documentType],
    queryFn: ({ signal }) =>
      api.get<PaginatedIssuedNumberList>("/issued-numbers/", {
        query: { document_type: documentType },
        signal,
      }),
  });
}

/** Example number and problems for settings that are not saved yet. */
export function useNumberingPreview(settings: NumberingPreviewRequest | null) {
  return useQuery<NumberingPreview, ApiError>({
    queryKey: [...numberingKey, "preview", settings],
    queryFn: ({ signal }) =>
      api.post<NumberingPreview>("/numbering-schemes/preview/", settings, { signal }),
    enabled: settings !== null,
    placeholderData: keepPreviousData,
  });
}

function useInvalidate() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: numberingKey });
}

export function useCreateScheme(idempotencyKey: string) {
  const invalidate = useInvalidate();
  return useMutation<NumberingScheme, ApiError, NumberingSchemeCreateRequest>({
    mutationFn: (body) =>
      api.post<NumberingScheme>("/numbering-schemes/", body, { idempotencyKey }),
    onSuccess: invalidate,
  });
}

export function useUpdateScheme(id: string) {
  const invalidate = useInvalidate();
  return useMutation<NumberingScheme, ApiError, NumberingSchemeUpdateRequest>({
    mutationFn: (body) => api.patch<NumberingScheme>(`/numbering-schemes/${id}/`, body),
    onSuccess: invalidate,
  });
}

export function useSetNextNumber(id: string, idempotencyKey: string) {
  const invalidate = useInvalidate();
  return useMutation<NumberingScheme, ApiError, SetNextNumberRequest>({
    mutationFn: (body) =>
      api.post<NumberingScheme>(`/numbering-schemes/${id}/next-number/`, body, {
        idempotencyKey,
      }),
    onSuccess: invalidate,
  });
}
