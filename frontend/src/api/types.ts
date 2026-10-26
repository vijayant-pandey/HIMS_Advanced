// Aliases over the types generated from docs/api/openapi.yaml (`npm run api:types`).
// Do not hand-write API shapes; regenerate when the backend contract changes.
import type { components } from "./schema";

type Schemas = components["schemas"];

export type CurrentUser = Schemas["CurrentUser"];
export type Grant = Schemas["Grant"];
export type Facility = Schemas["Facility"];
export type FacilityCreateRequest = Schemas["FacilityCreateRequest"];
export type PaginatedFacilityList = Schemas["PaginatedFacilityList"];
export type StaffMember = Schemas["StaffMember"];
export type PaginatedStaffMemberList = Schemas["PaginatedStaffMemberList"];
export type LoginRequest = Schemas["LoginRequest"];
export type InvitationDetails = Schemas["InvitationDetails"];
export type InvitationAcceptRequest = Schemas["InvitationAcceptRequest"];
export type PasswordResetDetails = Schemas["PasswordResetDetails"];
export type PasswordResetConfirmRequest = Schemas["PasswordResetConfirmRequest"];
export type PasswordResetRequested = Schemas["PasswordResetRequested"];
export type NoAccessReference = Schemas["NoAccessReference"];
