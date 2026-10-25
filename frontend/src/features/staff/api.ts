import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { ApiError, api } from "../../api/client";
import type { PaginatedStaffMemberList } from "../../api/types";

export function useStaff(search: string, page = 1) {
  return useQuery<PaginatedStaffMemberList, ApiError>({
    queryKey: ["staff", { search, page }],
    queryFn: ({ signal }) =>
      api.get<PaginatedStaffMemberList>("/staff/", { query: { search, page }, signal }),
    placeholderData: keepPreviousData,
  });
}
