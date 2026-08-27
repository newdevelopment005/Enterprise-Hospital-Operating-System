// Minimal Keycloak token client for the executive dashboard.
//
// ai-service fails closed: the /chat endpoint requires a valid bearer token
// issued by the `ehos` realm. The dashboard has no interactive login; it
// obtains a service token through the client-credentials grant and keeps it
// fresh (refresh-free: a new token is fetched shortly before expiry).
//
// The Vite dev server proxies `/auth` to the real Keycloak (http://localhost:8400)
// so browser requests stay same-origin (no CORS).

const REALM = (import.meta.env.VITE_KEYCLOAK_REALM as string | undefined) ?? 'ehos'
const CLIENT_ID = (import.meta.env.VITE_KEYCLOAK_CLIENT_ID as string | undefined) ?? 'ehos-api'
const CLIENT_SECRET =
  (import.meta.env.VITE_KEYCLOAK_CLIENT_SECRET as string | undefined) ?? 'ehos-client-2026'
const KEYCLOAK_BASE = (import.meta.env.VITE_KEYCLOAK_URL as string | undefined) ?? '/auth'

const TOKEN_KEY = 'ehos:executive-dashboard:token'

interface TokenRecord {
  access_token: string
  expires_at: number // epoch ms
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

function saveToken(access_token: string, expires_in: number): void {
  localStorage.setItem(
    TOKEN_KEY,
    JSON.stringify({
      access_token,
      // Refresh one minute before actual expiry.
      expires_at: Date.now() + Math.max(expires_in - 60, 30) * 1000,
    } satisfies TokenRecord),
  )
}

function tokenEndpoint(): string {
  return `${KEYCLOAK_BASE}/realms/${REALM}/protocol/openid-connect/token`
}

/** Non-expired bearer token for ai-service, fetching a new one when needed. */
export async function getValidToken(): Promise<string> {
  const cached = readToken()
  if (cached && cached.expires_at > Date.now()) return cached.access_token

  const res = await fetch(tokenEndpoint(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'client_credentials',
      client_id: CLIENT_ID,
      client_secret: CLIENT_SECRET,
    }),
  })
  if (!res.ok) throw new Error(`Token request failed (${res.status})`)
  const data = (await res.json()) as { access_token?: string; expires_in?: number }
  if (!data.access_token) throw new Error('Token response missing access_token')
  saveToken(data.access_token, data.expires_in ?? 300)
  return data.access_token
}
