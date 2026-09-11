/** Resolve a wall-clock input in the selected IANA timezone, independent of the browser zone. */
export function zonedLocalToIso(value: string, timezone: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value))
    throw new Error('Enter a complete date and time.');
  const nominal = Date.parse(`${value}:00Z`);
  if (!Number.isFinite(nominal)) throw new Error('Enter a valid date and time.');
  const formatter = new Intl.DateTimeFormat('en-GB', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });
  const local = (timestamp: number) => {
    const parts = Object.fromEntries(
      formatter.formatToParts(timestamp).map((p) => [p.type, p.value]),
    );
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
  };
  // Probe offsets on both sides of a transition so gaps and repeated hours are explicit.
  const offsets = new Set(
    [-86400000, 0, 86400000].map((delta) => {
      const probe = nominal + delta;
      return Date.parse(`${local(probe)}:00Z`) - probe;
    }),
  );
  const matches = [...offsets].map((offset) => nominal - offset).filter((t) => local(t) === value);
  if (!matches.length)
    throw new Error(
      `This local time does not exist in ${timezone}. Choose a time outside the daylight-saving change.`,
    );
  if (matches.length > 1)
    throw new Error(
      `This local time occurs twice in ${timezone}. Choose an unambiguous time outside the repeated hour.`,
    );
  return new Date(matches[0]).toISOString();
}
