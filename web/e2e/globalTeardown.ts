import { removeDataRoot } from "./env";

export default function globalTeardown(): void {
  removeDataRoot();
}
