export function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export function newId(prefix = "id"): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

/** An example request body built from an endpoint's JSON Schema.
 *
 * The curl sample used to print `-d '{...}'`, which is the one part a caller
 * can't guess — the field names, their types and which are required all live
 * in the schema the UI already has. Optional fields are included too, since a
 * sample you delete a line from is more useful than one you have to research.
 */
export function exampleRequestBody(schema: Record<string, unknown> | null | undefined): string {
  const properties = ((schema ?? {}) as { properties?: Record<string, Record<string, unknown>> })
    .properties;
  if (!properties || Object.keys(properties).length === 0) return "{}";

  const required = new Set(
    (((schema ?? {}) as { required?: string[] }).required ?? []) as string[]
  );

  const sample = (spec: Record<string, unknown>): unknown => {
    if ("default" in spec) return spec.default;
    if (Array.isArray(spec.enum) && spec.enum.length > 0) return spec.enum[0];
    switch (spec.type) {
      case "number":
      case "integer":
        return 1;
      case "boolean":
        return true;
      case "array":
        return [sample((spec.items as Record<string, unknown>) ?? { type: "string" })];
      case "object":
        return {};
      default:
        return "…";
    }
  };

  // Required first, so the shortest working request is the top of the object.
  const names = Object.keys(properties).sort(
    (a, b) => Number(required.has(b)) - Number(required.has(a))
  );
  // No trailing comments marking optional fields, however useful they'd read:
  // this string goes inside curl's -d, and a // comment makes the body invalid
  // JSON, so a copy-pasted sample would fail. Which fields are optional is
  // said outside the snippet instead.
  const lines = names.map((name, i) => {
    const value = JSON.stringify(sample(properties[name]));
    const comma = i < names.length - 1 ? "," : "";
    return `    ${JSON.stringify(name)}: ${value}${comma}`;
  });
  return `{\n${lines.join("\n")}\n  }`;
}

/** Names of an endpoint's optional fields, for a note beside the sample. */
export function optionalFields(schema: Record<string, unknown> | null | undefined): string[] {
  const properties = ((schema ?? {}) as { properties?: Record<string, unknown> }).properties ?? {};
  const required = new Set((((schema ?? {}) as { required?: string[] }).required ?? []) as string[]);
  return Object.keys(properties).filter((name) => !required.has(name));
}
