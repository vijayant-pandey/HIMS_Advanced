import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  LinearProgress,
  Link,
  Paper,
  Stack,
  Tab,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Typography,
} from "@mui/material";
import { type ReactNode, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";

import type { StaffMemberDetail } from "../../api/types";
import { ErrorAlert } from "../../components/ErrorAlert";
import { UserAccessPanel } from "../accessControl/UserAccessPanel";
import { useCurrentUser } from "../auth/api";
import { hasOrganizationWidePermission, hasPermission } from "../auth/grants";
import { useSendInvitation, useStaffMember } from "./api";
import { DocumentCell } from "./Documents";
import { EXPIRY, STATUS_COLOR, VERIFICATION } from "./labels";
import {
  AddCredentialDialog,
  AddPostingDialog,
  AddQualificationDialog,
  EditStaffDialog,
  EndPostingDialog,
  VerifyDialog,
} from "./StaffDialogs";

type Dialog =
  | { type: "edit" }
  | { type: "posting" }
  | { type: "endPosting"; id: string; label: string }
  | { type: "qualification" }
  | { type: "credential" }
  | { type: "verify"; kind: "qualification" | "credential"; id: string; label: string };

function Section({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Stack spacing={1}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="subtitle1" component="h2" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        {action}
      </Box>
      {children}
    </Stack>
  );
}

function Account({ staff, canManage }: { staff: StaffMemberDetail; canManage: boolean }) {
  const invite = useSendInvitation(staff.id);
  const { account } = staff;
  let state: { text: string; severity: "success" | "info" | "warning" };
  if (!account.has_login) {
    state = { text: "No sign-in account (no email recorded).", severity: "info" };
  } else if (!account.is_active) {
    state = { text: "Cannot sign in (account switched off).", severity: "warning" };
  } else if (account.activated) {
    state = {
      text: `Can sign in as ${account.email}. Two-factor: ${account.two_factor_enabled ? "on" : "off"}.`,
      severity: "success",
    };
  } else if (account.invitation_expires_at) {
    state = {
      text: `Invitation sent to ${account.email}; the link works until ${new Date(account.invitation_expires_at).toLocaleString()}.`,
      severity: "info",
    };
  } else {
    state = { text: `Not activated yet. Send an invitation to ${account.email}.`, severity: "warning" };
  }
  const canInvite = canManage && account.has_login && account.is_active && !account.activated;
  return (
    <Stack spacing={1}>
      <Alert
        severity={state.severity}
        action={
          canInvite && (
            <Button size="small" onClick={() => invite.mutate()} disabled={invite.isPending}>
              {account.invitation_expires_at ? "Resend invitation" : "Send invitation"}
            </Button>
          )
        }
      >
        {state.text}
      </Alert>
      {invite.data && (
        <Alert severity="success">Invitation emailed to {invite.data.email}.</Alert>
      )}
      {invite.error && <ErrorAlert error={invite.error} />}
    </Stack>
  );
}

export function StaffDetailPage() {
  const { id } = useParams();
  const { data: user } = useCurrentUser();
  const { data: staff, isPending, error } = useStaffMember(id);
  const [tab, setTab] = useState(0);
  const [dialog, setDialog] = useState<Dialog>();
  const close = () => setDialog(undefined);
  // Hints only: the API checks every permission.
  const canManage = hasOrganizationWidePermission(user, "staff.manage");
  const canVerify = hasPermission(user, "staff.credentials.verify");
  const canSeeAccess = hasPermission(user, "access.roles.view");
  const isSelf = !!staff?.user && staff.user === user?.id;

  if (isPending) return <LinearProgress />;
  if (error || !staff) return <ErrorAlert error={error} />;
  const name = `${staff.given_name} ${staff.family_name}`;
  const current = staff.department_assignments.filter((a) => a.is_current);
  const past = staff.department_assignments.filter((a) => !a.is_current);

  return (
    <Stack spacing={2}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/staff" underline="hover">
          Staff
        </Link>
        <Typography>{name}</Typography>
      </Breadcrumbs>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 2 }}>
        <Box>
          <Typography variant="h5" component="h1">
            {name}
          </Typography>
          <Stack direction="row" spacing={1} sx={{ mt: 0.5, alignItems: "center" }}>
            <Typography variant="body2">
              {staff.staff_type_label} · {staff.employee_number} · joined {staff.joined_on}
              {staff.left_on && ` · left ${staff.left_on}`}
            </Typography>
            <Chip
              size="small"
              color={STATUS_COLOR[staff.employment_status]}
              label={staff.employment_status_label}
            />
          </Stack>
        </Box>
        {canManage && (
          <Button variant="outlined" onClick={() => setDialog({ type: "edit" })}>
            Edit
          </Button>
        )}
      </Box>
      <Account staff={staff} canManage={canManage} />

      <Tabs value={tab} onChange={(_, value: number) => setTab(value)} aria-label="Staff sections">
        <Tab label={`Departments (${current.length})`} />
        <Tab label={`Qualifications (${staff.qualifications.length})`} />
        <Tab label={`Licences (${staff.credentials.length})`} />
        {canSeeAccess && staff.user && <Tab label="Access" />}
      </Tabs>

      {tab === 0 && (
        <Section
          title="Department postings"
          action={
            canManage && (
              <Button size="small" variant="contained" onClick={() => setDialog({ type: "posting" })}>
                Add posting
              </Button>
            )
          }
        >
          <TableContainer component={Paper}>
            <Table size="small" aria-label="Department postings">
              <TableHead>
                <TableRow>
                  <TableCell>Department</TableCell>
                  <TableCell>Designation</TableCell>
                  <TableCell>Specialty</TableCell>
                  <TableCell>From</TableCell>
                  <TableCell>Until</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {[...current, ...past].map((a) => (
                  <TableRow key={a.id} sx={{ opacity: a.is_current ? 1 : 0.6 }}>
                    <TableCell>
                      {a.department_name}
                      <Typography variant="caption" component="p">
                        {a.facility_name}
                        {a.is_primary && " · main department"}
                      </Typography>
                    </TableCell>
                    <TableCell>{a.designation_name}</TableCell>
                    <TableCell>{a.specialty_name ?? "—"}</TableCell>
                    <TableCell>{a.valid_from}</TableCell>
                    <TableCell>{a.valid_until ?? "—"}</TableCell>
                    <TableCell align="right">
                      {canManage && a.is_current && (
                        <Button
                          size="small"
                          onClick={() =>
                            setDialog({ type: "endPosting", id: a.id, label: a.department_name })
                          }
                        >
                          End
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {staff.department_assignments.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6}>No department postings yet.</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Section>
      )}

      {tab === 1 && (
        <Section
          title="Qualifications"
          action={
            canManage && (
              <Button
                size="small"
                variant="contained"
                onClick={() => setDialog({ type: "qualification" })}
              >
                Add qualification
              </Button>
            )
          }
        >
          <TableContainer component={Paper}>
            <Table size="small" aria-label="Qualifications">
              <TableHead>
                <TableRow>
                  <TableCell>Qualification</TableCell>
                  <TableCell>Institution</TableCell>
                  <TableCell>Year</TableCell>
                  <TableCell>Verification</TableCell>
                  <TableCell>Documents</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {staff.qualifications.map((q) => {
                  const v = VERIFICATION[q.verification_status] ?? VERIFICATION.unverified!;
                  return (
                    <TableRow key={q.id}>
                      <TableCell>
                        {q.qualification_type_name}
                        {q.specialty_name && (
                          <Typography variant="caption" component="p">
                            {q.specialty_name}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>{q.institution}</TableCell>
                      <TableCell>{q.year_awarded}</TableCell>
                      <TableCell>
                        <Chip size="small" color={v.color} label={v.label} />
                        {q.verified_by_name && (
                          <Typography variant="caption" component="p">
                            by {q.verified_by_name}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <DocumentCell
                          staffId={staff.id}
                          documents={staff.documents.filter((d) => d.qualification === q.id)}
                          target={{ qualification: q.id }}
                          label={q.qualification_type_name}
                          canManage={canManage}
                        />
                      </TableCell>
                      <TableCell align="right">
                        {canVerify && !isSelf && q.verification_status === "unverified" && (
                          <Button
                            size="small"
                            onClick={() =>
                              setDialog({
                                type: "verify",
                                kind: "qualification",
                                id: q.id,
                                label: q.qualification_type_name,
                              })
                            }
                          >
                            Verify
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
                {staff.qualifications.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6}>No qualifications recorded.</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Section>
      )}

      {tab === 2 && (
        <Section
          title="Licences and registrations"
          action={
            canManage && (
              <Button size="small" variant="contained" onClick={() => setDialog({ type: "credential" })}>
                Add licence
              </Button>
            )
          }
        >
          <TableContainer component={Paper}>
            <Table size="small" aria-label="Licences">
              <TableHead>
                <TableRow>
                  <TableCell>Type</TableCell>
                  <TableCell>Number</TableCell>
                  <TableCell>Issued by</TableCell>
                  <TableCell>Expires</TableCell>
                  <TableCell>Verification</TableCell>
                  <TableCell>Documents</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {staff.credentials.map((c) => {
                  const v = VERIFICATION[c.verification_status] ?? VERIFICATION.unverified!;
                  const e = EXPIRY[c.expiry_state] ?? EXPIRY.no_expiry!;
                  return (
                    <TableRow key={c.id}>
                      <TableCell>{c.credential_type_label}</TableCell>
                      <TableCell>
                        {c.registration_number}
                        <Typography variant="caption" component="p">
                          {c.jurisdiction}
                        </Typography>
                      </TableCell>
                      <TableCell>{c.issuing_authority}</TableCell>
                      <TableCell>
                        {c.expires_at ?? "—"}
                        <Box>
                          <Chip size="small" variant="outlined" color={e.color} label={e.label} />
                        </Box>
                      </TableCell>
                      <TableCell>
                        <Chip size="small" color={v.color} label={v.label} />
                        {c.verified_by_name && (
                          <Typography variant="caption" component="p">
                            by {c.verified_by_name}
                          </Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <DocumentCell
                          staffId={staff.id}
                          documents={staff.documents.filter((d) => d.credential === c.id)}
                          target={{ credential: c.id }}
                          label={c.credential_type_label}
                          canManage={canManage}
                        />
                      </TableCell>
                      <TableCell align="right">
                        {canVerify && !isSelf && c.verification_status === "unverified" && (
                          <Button
                            size="small"
                            onClick={() =>
                              setDialog({
                                type: "verify",
                                kind: "credential",
                                id: c.id,
                                label: c.credential_type_label,
                              })
                            }
                          >
                            Verify
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
                {staff.credentials.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7}>No licences recorded.</TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Section>
      )}

      {tab === 3 && staff.user && (
        <Section title="Access to HIMS">
          <UserAccessPanel userId={staff.user} personName={name} />
        </Section>
      )}

      {dialog?.type === "edit" && <EditStaffDialog staff={staff} onClose={close} />}
      {dialog?.type === "posting" && <AddPostingDialog staffId={staff.id} onClose={close} />}
      {dialog?.type === "endPosting" && (
        <EndPostingDialog
          staffId={staff.id}
          assignmentId={dialog.id}
          label={dialog.label}
          onClose={close}
        />
      )}
      {dialog?.type === "qualification" && (
        <AddQualificationDialog staffId={staff.id} onClose={close} />
      )}
      {dialog?.type === "credential" && <AddCredentialDialog staffId={staff.id} onClose={close} />}
      {dialog?.type === "verify" && (
        <VerifyDialog
          staffId={staff.id}
          kind={dialog.kind}
          itemId={dialog.id}
          label={dialog.label}
          onClose={close}
        />
      )}
    </Stack>
  );
}
