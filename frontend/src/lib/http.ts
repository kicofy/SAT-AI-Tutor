import axios from "axios";
import { env } from "./env";
import { getClientToken } from "./auth-storage";

const api = axios.create({
  baseURL: env.apiBaseUrl.replace(/\/$/, ""),
  timeout: 15_000,
});

api.interceptors.request.use((config) => {
  const token = getClientToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event("sat:auth-expired"));
    }
    return Promise.reject(error);
  }
);

export { api };

