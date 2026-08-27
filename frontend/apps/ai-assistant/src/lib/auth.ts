// Minimal Keycloak token client for HospitalGPT.
//
// ai-service fails closed: every data endpoint requires a valid bearer token
// issued by the `ehos` realm. This module obtains one with the password grant
// and keeps it fresh (refresh token rotation).
//
// The Vite dev server proxies `/auth` to the real Keycloak (http://localhost:8400)
// so browser requests stay same-origin (no CORS).

const REALM = (import.meta.env.VITE_KEYCLOAK_REALM as string | undefined) ?? 'ehos'
const CLIENT_ID = (import.meta.env.VITE_KEYCLOAK_CLIENT_ID as string | undefined) ?? 'ehos-api'
const CLIENT_SECRET = (import.meta.env.VITE_KEYCLOAK_CLIENT_SECRET as string | undefined) ?? 'ehos-client-2026'
const KEYCLOAK_BASE = (import.meta.env.VITE_KEYCLOAK_URL as string | undefined) ?? '/auth'

const TOKEN_KEY = 'ehos:hospitalgpt:token'

export class AuthError extends Error {
  constructor(message = 'Not authenticated') {
    super(message)
    this.name = 'AuthError'
  }
}

interface TokenRecord {
  access_token: string
  refresh_token: string
  expires_at: number // epoch ms
}

function tokenEndpoint(): string {
  return `${KEYCLOAK_BASE}/realms/${REALM}/protocol/openid-connect/token`
}

function readToken(): TokenRecord | null {
  const raw = localStorage.getItem(TOKEN_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as TokenRecord
  } catch {
    return null
  }
}

function saveToken(access_token: string, refresh_token: string, expires_in: number): void {
  localStorage.setItem(
    TOKEN_KEY,
    JSON.stringify({
      access_token,
      refresh_token,
      expires_at: Date.now() + expires_in * 1000,
    } satisfies TokenRecord),
  )
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

/** True when a non-expired token is already stored (no network call). */
export function hasToken(): boolean {
  const t = readToken()
  return !!t && t.expires_at > Date.now()
}

/** Exchange a Keycloak password grant for an access token and store it. */
export async function login(username: string, password: string): Promise<string> {
  const res = await fetch(tokenEndpoint(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'password',
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
      username,
      password,
      scope: 'openid',
    }),
  })
  if (res.status === 401 || res.status === 403) {
    throw new AuthError('Invalid username or password')
  }
  if (!res.ok) throw new Error(`Login failed (${res.status})`)
  const text = await res.text()
  let data: { access_token?: string; refresh_token?: string; expires_in?: number }
  try {
    data = JSON.parse(text)
  } catch {
    throw new Error('Sign-in service unavailable — is Keycloak running on port 8400?')
  }
  saveToken(data.access_token ?? '', data.refresh_token ?? '', data.expires_in ?? 300)
  return data.access_token as string
}

/** Non-expired access token, refreshing through the refresh token when needed. */
export async function getValidToken(): Promise<string> {
  const t = readToken()
  if (t && t.expires_at > Date.now()) return t.access_token
  if (t?.refresh_token) {
    try {
      const res = await fetch(tokenEndpoint(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          grant_type: 'refresh_token',
          client_id: CLIENT_ID,
          client_secret: CLIENT_SECRET,
          refresh_token: t.refresh_token,
        }),
      })
      if (res.ok) {
        const data = await res.json()
        saveToken(data.access_token, data.refresh_token, data.expires_in)
        return data.access_token as string
      }
      clearToken()
    } catch {
      clearToken()
    }
  }
  throw new AuthError()
}