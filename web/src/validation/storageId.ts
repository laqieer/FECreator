const reservedStorageIds = new Set(["locks", ".locks"]);
const windowsReservedDeviceNames = new Set([
  "con",
  "prn",
  "aux",
  "nul",
  ...Array.from({ length: 9 }, (_, index) => `com${index + 1}`),
  ...Array.from({ length: 9 }, (_, index) => `lpt${index + 1}`),
]);

export function portableStorageIdError(value: string): string | null {
  if (value !== value.trim()) {
    return "must not have leading or trailing whitespace.";
  }
  if (value === "") {
    return "must be a non-empty string.";
  }
  if (/^[\\/]/.test(value) || (value.length >= 2 && value[1] === ":")) {
    return "must not be absolute.";
  }
  if (value === "." || value === "..") {
    return "must not be '.' or '..'.";
  }
  if (value.startsWith(".")) {
    return "must not start with '.'.";
  }
  if (reservedStorageIds.has(value)) {
    return "uses a reserved namespace.";
  }
  if (value.includes("/") || value.includes("\\")) {
    return "must not contain path separators.";
  }
  if (/[. ]$/.test(value)) {
    return "must not end with '.' or a space.";
  }
  const basename = value.split(".", 1)[0]!.toLowerCase();
  if (windowsReservedDeviceNames.has(basename)) {
    return "uses a reserved device name.";
  }
  return null;
}
