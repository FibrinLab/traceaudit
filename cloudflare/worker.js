// Routes every request to a single long-lived container running `traceaudit serve` on port 8080.
// Note: the container's disk is ephemeral; finished jobs disappear when it sleeps. For durable results,
// run the image on a host with a volume (docker compose, Fly, Render) or sync /data to R2.
import { Container, getContainer } from "@cloudflare/containers";

export class TraceauditContainer extends Container {
  defaultPort = 8080;
  sleepAfter = "30m";
  envVars = {
    TRACEAUDIT_OPERATOR_KEYS: this.env?.TRACEAUDIT_OPERATOR_KEYS ?? "anthropic=ANTHROPIC_API_KEY",
    TRACEAUDIT_ALLOW_CLIENTS: this.env?.TRACEAUDIT_ALLOW_CLIENTS ?? "sim,anthropic",
    TRACEAUDIT_ANONYMOUS: this.env?.TRACEAUDIT_ANONYMOUS ?? "all",
    TRACEAUDIT_MAX_CALLS_PER_JOB: this.env?.TRACEAUDIT_MAX_CALLS_PER_JOB ?? "200",
    TRACEAUDIT_MAX_CALLS_PER_DAY: this.env?.TRACEAUDIT_MAX_CALLS_PER_DAY ?? "2000",
    ANTHROPIC_API_KEY: this.env?.ANTHROPIC_API_KEY ?? "",
  };
}

export default {
  async fetch(request, env) {
    const container = getContainer(env.TRACEAUDIT, "main");
    return container.fetch(request);
  },
};
