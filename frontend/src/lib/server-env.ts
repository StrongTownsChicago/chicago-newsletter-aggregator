/** Server-only secrets, read from the Cloudflare runtime env or, in local dev, import.meta.env. */
export type ServerSecretName = "SUPABASE_SERVICE_KEY" | "UNSUBSCRIBE_SECRET_KEY";

/** The named secret, or undefined when neither source sets it. */
export function readServerSecret(
  locals: Pick<App.Locals, "runtime"> | undefined,
  name: ServerSecretName,
): string | undefined {
  const runtimeValue = locals?.runtime?.env?.[name];
  const runtimeSecret = typeof runtimeValue === "string" ? runtimeValue : "";
  return runtimeSecret || import.meta.env[name] || undefined;
}
