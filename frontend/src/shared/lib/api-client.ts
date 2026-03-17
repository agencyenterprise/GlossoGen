import createClient from "openapi-fetch";
import type { paths } from "@/types/api.gen";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createClient<paths>({
  baseUrl: API_URL,
});
