import { afterEach, describe, expect, it, vi } from "vitest";
import { readServerSecret } from "../../lib/server/server-env";

const withRuntimeEnv = (env: Record<string, unknown>) =>
  ({ runtime: { env } }) as unknown as Pick<App.Locals, "runtime">;

describe("readServerSecret", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("prefers the Cloudflare runtime env", () => {
    vi.stubEnv("UNSUBSCRIBE_SECRET_KEY", "local-secret");
    const locals = withRuntimeEnv({ UNSUBSCRIBE_SECRET_KEY: "runtime-secret" });
    expect(readServerSecret(locals, "UNSUBSCRIBE_SECRET_KEY")).toBe("runtime-secret");
  });

  it("falls back to import.meta.env when the runtime value is missing or empty", () => {
    vi.stubEnv("SUPABASE_SERVICE_KEY", "local-key");
    expect(readServerSecret(undefined, "SUPABASE_SERVICE_KEY")).toBe("local-key");
    expect(readServerSecret(withRuntimeEnv({}), "SUPABASE_SERVICE_KEY")).toBe("local-key");
    expect(
      readServerSecret(withRuntimeEnv({ SUPABASE_SERVICE_KEY: "" }), "SUPABASE_SERVICE_KEY"),
    ).toBe("local-key");
  });

  it("ignores a non-string runtime value", () => {
    vi.stubEnv("SUPABASE_SERVICE_KEY", "local-key");
    const locals = withRuntimeEnv({ SUPABASE_SERVICE_KEY: { binding: true } });
    expect(readServerSecret(locals, "SUPABASE_SERVICE_KEY")).toBe("local-key");
  });

  it("returns undefined when neither source sets the secret", () => {
    vi.stubEnv("UNSUBSCRIBE_SECRET_KEY", "");
    expect(readServerSecret(undefined, "UNSUBSCRIBE_SECRET_KEY")).toBeUndefined();
  });
});
