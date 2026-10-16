/** Server-only secrets, read from the Cloudflare runtime env or, in local dev, import.meta.env. */
export type ServerSecretName = "SUPABASE_SERVICE_KEY" | "UNSUBSCRIBE_SECRET_KEY";

// Each read is written out in full: the build substitutes only literal
// `import.meta.env.NAME` reads of server-only variables. A computed key reads
// a copy of import.meta.env that holds only public variables.
const readBuildEnvSecret: Record<ServerSecretName, () => string | undefined> = {
  SUPABASE_SERVICE_KEY: () => import.meta.env.SUPABASE_SERVICE_KEY,
  UNSUBSCRIBE_SECRET_KEY: () => import.meta.env.UNSUBSCRIBE_SECRET_KEY,
};

/** The named secret, or undefined when neither source sets it. */
export function readServerSecret(
  locals: Pick<App.Locals, "runtime"> | undefined,
  name: ServerSecretName,
): string | undefined {
  const runtimeValue = locals?.runtime?.env?.[name];
  const runtimeSecret = typeof runtimeValue === "string" ? runtimeValue : "";
  return runtimeSecret || readBuildEnvSecret[name]() || undefined;
}
