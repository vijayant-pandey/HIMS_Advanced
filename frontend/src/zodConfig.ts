// Zod normally tests whether `new Function` works, to compile its checks. Our content security
// policy forbids that (HIMS-SEC-012), so the test would fill the block reports on every page load.
// Validation behaves the same without it. Import this before anything that defines a schema.
import { z } from "zod";

z.config({ jitless: true });
