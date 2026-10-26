import { zodResolver } from "@hookform/resolvers/zod";
import { Button, Stack, TextField } from "@mui/material";
import { useEffect, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "../../api/client";
import { ErrorAlert } from "../../components/ErrorAlert";

const schema = z
  .object({
    password: z.string().min(12, "Use at least 12 characters"),
    confirm: z.string(),
  })
  .refine((values) => values.password === values.confirm, {
    path: ["confirm"],
    message: "Passwords do not match",
  });
type FormValues = z.infer<typeof schema>;

interface Props {
  intro: ReactNode;
  submitLabel: string;
  pending: boolean;
  error: ApiError | null;
  onSubmit: (password: string) => void;
}

/** "Choose a password" form shared by account activation and password reset. */
export function NewPasswordForm({ intro, submitLabel, pending, error, onSubmit }: Props) {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  // Server-side password rules (e.g. "too common", "too similar to your email") come back
  // per field; show them under the password box.
  useEffect(() => {
    const message = error?.problem.errors?.find((e) => e.field === "password")?.message;
    if (message) setError("password", { message });
  }, [error, setError]);

  return (
    <form onSubmit={handleSubmit(({ password }) => onSubmit(password))} noValidate>
      <Stack spacing={2}>
        {intro}
        {error && !error.problem.errors && <ErrorAlert error={error} />}
        <TextField
          label="New password"
          type="password"
          autoComplete="new-password"
          autoFocus
          error={!!errors.password}
          helperText={
            errors.password?.message ?? "At least 12 characters. Avoid common words and your name."
          }
          {...register("password")}
        />
        <TextField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          error={!!errors.confirm}
          helperText={errors.confirm?.message}
          {...register("confirm")}
        />
        <Button type="submit" variant="contained" disabled={pending}>
          {submitLabel}
        </Button>
      </Stack>
    </form>
  );
}
