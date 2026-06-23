/**
 * nexus-js / auth.ts
 * ────────────────────
 * AuthClient — all authentication endpoints.
 *
 * Accessed via `nexus.auth.*` on a NexusClient instance.
 */

import type { NexusClient } from "./client";
import type { PlayerResponse, TokenResponse } from "./types";
import { NexusError } from "./types";

export class AuthClient {
  constructor(private c: NexusClient) {}

  /**
   * Create a new registered player account.
   *
   * Does NOT log the player in — call `.login()` afterward to obtain tokens.
   * Throws NexusError (409, code "USERNAME_TAKEN" / "EMAIL_TAKEN") on conflict.
   */
  async register(username: string, email: string, password: string): Promise<PlayerResponse> {
    return this.c.fetch<PlayerResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, email, password }),
    });
  }

  /**
   * Authenticate with username/password and obtain a token pair.
   *
   * On success, the access token is automatically attached to the client's
   * HTTP transport — every subsequent call on this NexusClient (and its
   * sub-clients) is authenticated with no further setup.
   *
   * Throws NexusError (401 "INVALID_CREDENTIALS", or 423 "ACCOUNT_LOCKED"
   * after 5 consecutive failures).
   */
  async login(username: string, password: string): Promise<TokenResponse> {
    const token = await this.c.fetch<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    this.c.setToken(token.access_token);
    this.c.refreshToken = token.refresh_token;
    return token;
  }

  /**
   * Create an anonymous guest account and log in immediately.
   *
   * Returns a full token pair — no separate login call needed. The access
   * token is automatically attached to the client.
   */
  async guest(): Promise<TokenResponse> {
    const token = await this.c.fetch<TokenResponse>("/auth/guest", { method: "POST" });
    this.c.setToken(token.access_token);
    this.c.refreshToken = token.refresh_token;
    return token;
  }

  /**
   * Exchange a refresh token for a new access/refresh token pair.
   *
   * If `refreshToken` is omitted, uses the refresh token stored from the
   * last login()/guest() call.
   *
   * Throws NexusError (401) if the refresh token is invalid, expired, or
   * already revoked (one-time use — calling refresh() twice with the same
   * token fails the second time).
   */
  async refresh(refreshToken?: string): Promise<TokenResponse> {
    const tokenToUse = refreshToken ?? this.c.refreshToken;
    if (tokenToUse === null || tokenToUse === undefined) {
      throw new NexusError(
        "No refresh token available. Call login() or guest() first, or pass refreshToken explicitly.",
      );
    }

    const token = await this.c.fetch<TokenResponse>("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token: tokenToUse }),
    });
    this.c.setToken(token.access_token);
    this.c.refreshToken = token.refresh_token;
    return token;
  }

  /**
   * Invalidate the current session's tokens.
   *
   * Both the access token and refresh token are blacklisted server-side.
   * After this call, `nexus.accessToken` is null. Safe to call even with
   * no active session — it's a no-op in that case (no network call is made).
   */
  async logout(refreshToken?: string): Promise<void> {
    const tokenToUse = refreshToken ?? this.c.refreshToken;
    if (tokenToUse !== null && tokenToUse !== undefined) {
      await this.c.fetch<void>("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: tokenToUse }),
      });
    }
    this.c.clearToken();
    this.c.refreshToken = null;
  }
}
